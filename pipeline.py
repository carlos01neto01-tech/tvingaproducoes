"""Pipeline local de prova de conceito: transcrição, sugestões por heurísticas e MP4 legendado.

ATENÇÃO: Não reproduz automaticamente uma timeline de After Effects/Premiere,
não avalia veracidade jornalística e não publica conteúdos.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path


def require_ffmpeg() -> None:
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('FFmpeg e ffprobe não encontrados no PATH. Instale FFmpeg antes de processar.')


def ffmpeg_duration(input_file: Path) -> float:
    require_ffmpeg()
    cmd=['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(input_file)]
    result=subprocess.run(cmd,capture_output=True,text=True,check=True,timeout=30)
    duration=float(result.stdout.strip())
    if not math.isfinite(duration) or duration<=0:
        raise ValueError('Vídeo com duração inválida.')
    return duration


def transcribe(input_file:Path, work:Path)->list[dict]:
    """Transcreve em português. faster-whisper baixa os pesos na primeira execução."""
    require_ffmpeg()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError('faster-whisper não instalado. Execute: pip install -r requirements.txt') from exc
    wav=work/'audio.wav'
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(input_file),'-vn','-ac','1','-ar','16000',str(wav)],check=True,timeout=5400)
    model_name=os.getenv('WHISPER_MODEL','base')
    model=WhisperModel(model_name,device='cpu',compute_type='int8')
    transcribed,_=model.transcribe(str(wav),language='pt',beam_size=3,vad_filter=True,word_timestamps=True)
    segments=[]
    for s in transcribed:
        words=[{'start':float(w.start),'end':float(w.end),'text':str(w.word)} for w in (s.words or []) if w.start is not None and w.end is not None]
        text=str(s.text or '').strip()
        if text:
            segments.append({'start':float(s.start),'end':float(s.end),'text':text,'words':words})
    wav.unlink(missing_ok=True)
    return segments


def clip_score(text:str, duration:float)->float:
    """Pontuação técnica simples: não é um classificador de potencial viral."""
    tokens=re.findall(r'\w+',text.lower())
    if not tokens:return 0.0
    keyword_bonus=sum(w in {'importante','atenção','entenda','porquê','por','exemplo','mudou','agora','como','quando','descoberta','impacto','resultado','segredo'} for w in tokens)
    diversity=len(set(tokens))/max(1,len(tokens))
    speech_rate=len(tokens)/max(1,duration)
    return (min(len(tokens),130)*0.17+min(keyword_bonus,5)*1.3 + diversity*6 + (2 if '?' in text else 0) + (2 if '!' in text else 0) - abs(speech_rate-2.0)*2)


def suggest_clips(segments:list[dict], target:int=10, min_seconds:int=18, max_seconds:int=70)->list[dict]:
    """Produz até target sugestões, evitando sobreposição significativa."""
    if not segments:return []
    target=max(1,min(20,int(target)))
    candidates=[]
    n=len(segments)
    for i in range(0,n,2):
        start=max(0,float(segments[i]['start']))
        end=start
        texts=[]
        for j in range(i,n):
            seg=segments[j]
            finish=float(seg['end'])
            if finish-start>max_seconds and texts:break
            texts.append(str(seg.get('text','')))
            end=finish
            if end-start>=min_seconds:
                text=' '.join(texts)
                candidates.append({'start':round(start,2),'end':round(end,2),'text':text,'score':clip_score(text,end-start)})
                if end-start>=32:break
    candidates.sort(key=lambda c:(-c['score'],c['start']))
    chosen=[]
    for c in candidates:
        if any(max(0,min(c['end'],x['end'])-max(c['start'],x['start']))>min(c['end']-c['start'],x['end']-x['start'])*.14 for x in chosen):
            continue
        short=' '.join(c['text'].split()[:11]).rstrip('.,:;!?')
        c['title']=(short[:85]+'…') if len(short)>85 else short
        c['id']=f'clip-{len(chosen)+1:02d}'
        chosen.append(c)
        if len(chosen)>=target:break
    return chosen


def ass_timestamp(seconds:float)->str:
    total=max(0,int(round(seconds*100)))
    h,rem=divmod(total,360000)
    m,rem=divmod(rem,6000)
    s,cs=divmod(rem,100)
    return f'{h}:{m:02d}:{s:02d}.{cs:02d}'


def ass_color(hexcolor:str)->str:
    if not isinstance(hexcolor,str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',hexcolor):
        return '&H00FFFFFF'
    rr,gg,bb=hexcolor[1:3],hexcolor[3:5],hexcolor[5:7]
    return f'&H00{bb}{gg}{rr}'.upper()


def ass_escape(text:str)->str:
    return text.replace('\\','').replace('{','(').replace('}',')').replace('\n',' ').strip()


def make_caption_events(segments:list[dict],start:float,end:float,maxwords:int=7)->list[dict]:
    """Distribui legendas por timestamps das palavras, com fallback por segmento."""
    words=[]
    for seg in segments:
        if seg['end']<=start or seg['start']>=end:continue
        if seg.get('words'):
            words.extend([{'start':max(start,float(w['start'])),'end':min(end,float(w['end'])),'text':w['text'].strip()} for w in seg['words'] if w['end']>start and w['start']<end])
        else:
            ws=seg['text'].split()
            begin=max(start,float(seg['start']));finish=min(end,float(seg['end']))
            if not ws:continue
            step=(finish-begin)/len(ws)
            words.extend([{'start':begin+i*step,'end':begin+(i+1)*step,'text':word} for i,word in enumerate(ws)])
    if not words:return []
    maxwords=max(2,min(15,int(maxwords)))
    result=[]
    for i in range(0,len(words),maxwords):
        group=words[i:i+maxwords]
        if not group:continue
        a=max(0,group[0]['start']-start);b=max(a+.12,group[-1]['end']-start)
        result.append({'start':a,'end':b,'text':' '.join(w['text'] for w in group)})
    return result


def create_ass(segments:list[dict],start:float,end:float,preset:dict,dest:Path,title:str="")->None:
    primary=ass_color(preset.get('primary','#FFFFFF'))
    accent=ass_color(preset.get('accent','#9885FF'))
    font=preset.get('font','Arial')
    if font not in {'Arial','DejaVu Sans','Liberation Sans'}:font='Arial'
    alignment={'bottom':2,'middle':5,'top':8}.get(preset.get('position'),2)
    anim=preset.get('animation','fade')
    words=max(2,min(15,int(preset.get('maxWords',7))))
    lines=["[Script Info]","ScriptType: v4.00+","PlayResX: 720","PlayResY: 1280","WrapStyle: 2","ScaledBorderAndShadow: yes","","[V4+ Styles]","Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",f'Style: Default,{font},46,{primary},{accent},&H000B0B16,&H60000000,-1,0,0,0,100,100,0,0,1,4,2,{alignment},42,42,145,1',f'Style: Headline,{font},40,{primary},{accent},&H000B0B16,&H60000000,-1,0,0,0,100,100,0,0,1,3,2,8,45,45,135,1',"","[Events]","Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    headline=ass_escape(title)[:110]
    if headline:
        hold=min(4.5,end-start)
        lines.append(f"Dialogue: 1,0:00:00.00,{ass_timestamp(hold)},Headline,,0,0,0,,{{\\fad(180,220)}}{headline}")
    for ev in make_caption_events(segments,start,end,words):
        raw=ass_escape(ev['text'])
        if not raw:continue
        if preset.get('uppercase'):raw=raw.upper()
        tokenized=raw.split()
        idx=max(range(len(tokenized)),key=lambda i:len(tokenized[i])) if tokenized else -1
        if idx>=0 and len(tokenized[idx])>=6:
            tokenized[idx]=f'{{\\c{accent}}}'+tokenized[idx]+f'{{\\c{primary}}}'
        styleText=' '.join(tokenized)
        if anim=='fade':styleText='{\\fad(140,120)}'+styleText
        elif anim=='pop':styleText='{\\fscx90\\fscy90\\t(0,180,\\fscx100\\fscy100)}'+styleText
        lines.append(f"Dialogue: 0,{ass_timestamp(ev['start'])},{ass_timestamp(ev['end'])},Default,,0,0,0,,{styleText}")
    dest.write_text('\n'.join(lines)+'\n',encoding='utf-8')


def render_video(input_file:Path,jobdir:Path,segments:list[dict],clip:dict,preset:dict,title:str="")->Path:
    require_ffmpeg()
    start=max(0,float(clip['start']));end=float(clip['end'])
    if end<=start:raise ValueError('Trecho inválido')
    duration=ffmpeg_duration(input_file)
    if end>duration+0.25:raise ValueError('O corte ultrapassa a duração do vídeo.')
    output=jobdir/f"{clip['id']}.mp4"
    assfile=jobdir/f"{clip['id']}.ass"
    create_ass(segments,start,end,preset,assfile,title=title)
    escaped=str(assfile.resolve()).replace('\\','\\\\').replace(':','\\:').replace("'", "\\'")
    video_filter=f"scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,subtitles=filename='{escaped}'"
    cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',f'{start:.3f}','-i',str(input_file),'-t',f'{end-start:.3f}','-vf',video_filter,'-c:v','libx264','-preset','veryfast','-crf','25','-c:a','aac','-b:a','128k','-movflags','+faststart',str(output)]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=7200)
    if result.returncode!=0:
        raise RuntimeError('FFmpeg não conseguiu renderizar: '+result.stderr[-650:])
    return output


def save_transcript(segments:list[dict],jobdir:Path)->None:
    (jobdir/'transcription.json').write_text(json.dumps(segments,ensure_ascii=False,indent=2),encoding='utf-8')
