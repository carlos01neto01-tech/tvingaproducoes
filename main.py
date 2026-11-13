"""API local FastAPI para o piloto TV Ingá Studio. Não expor publicamente sem autenticação."""
from __future__ import annotations

import json
import os
import re
import threading
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pipeline import ffmpeg_duration, render_video, save_transcript, suggest_clips, transcribe

BASE=Path(__file__).resolve().parent.parent
WORK=Path(os.getenv('STUDIO_WORKSPACE',str(BASE/'backend'/'workspace'))).resolve()
WORK.mkdir(parents=True,exist_ok=True)
MAX_BYTES=int(os.getenv('MAX_UPLOAD_MB','2048'))*1024*1024
ALLOWED={'.mp4','.mov','.mkv','.webm'}
SLUGS={p['slug'] for p in json.loads((BASE/'docs'/'data'/'programs.json').read_text(encoding='utf-8'))}
jobs:dict[str,dict]={}
lock=threading.RLock()
app=FastAPI(title='TV Ingá Studio API',version='0.1.0',description='Backend de teste local; não é um serviço pronto para produção.')
origins=[x.strip() for x in os.getenv('ALLOWED_ORIGINS','http://localhost:8080,http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,allow_methods=['GET','POST'],allow_headers=['Content-Type'])

class RenderRequest(BaseModel):
    title:str=Field(default='',max_length=160)
    preset:dict=Field(default_factory=dict)
    start:float|None=None
    end:float|None=None

def public_job(job:dict)->dict:
    return {key:job.get(key) for key in ('id','program_slug','status','error','duration','suggestions','filename')}

@app.get('/api/health')
def health():
    return {'ok':True,'version':'0.1.0','mode':'local-pilot'}

@app.post('/api/jobs',status_code=202)
async def new_job(background_tasks:BackgroundTasks,file:UploadFile=File(...),program_slug:str=Form(...),target_clips:int=Form(10)):
    if program_slug not in SLUGS:raise HTTPException(400,'Programa desconhecido.')
    if not 1<=target_clips<=20:raise HTTPException(400,'Escolha entre 1 e 20 cortes.')
    suffix=Path(file.filename or '').suffix.lower()
    if suffix not in ALLOWED:raise HTTPException(415,'Formato não aceito. Use MP4, MOV, MKV ou WebM.')
    jobid=uuid.uuid4().hex
    jobdir=WORK/jobid
    jobdir.mkdir(parents=True,exist_ok=True)
    videofile=jobdir/f'input{suffix}'
    total=0
    try:
        with videofile.open('wb') as out:
            while True:
                piece=await file.read(1024*1024)
                if not piece:break
                total+=len(piece)
                if total>MAX_BYTES:raise HTTPException(413,'Arquivo excede o limite de tamanho configurado.')
                out.write(piece)
        if total<1024:raise HTTPException(400,'Arquivo vazio ou muito pequeno.')
    except Exception:
        videofile.unlink(missing_ok=True)
        try:jobdir.rmdir()
        except OSError:pass
        raise
    finally:
        await file.close()
    job={'id':jobid,'program_slug':program_slug,'status':'queued','error':None,'duration':None,'suggestions':[],'filename':Path(file.filename or 'video').name,'file':str(videofile),'segments':[]}
    with lock:jobs[jobid]=job
    background_tasks.add_task(process_job,jobid,target_clips)
    return public_job(job)

def process_job(jobid:str,target_clips:int):
    with lock:
        job=jobs[jobid];job['status']='running'
    try:
        videofile=Path(job['file']);jobdir=videofile.parent
        duration=ffmpeg_duration(videofile)
        segments=transcribe(videofile,jobdir)
        save_transcript(segments,jobdir)
        suggestions=suggest_clips(segments,target_clips)
        with lock:
            job.update(duration=round(duration,2),segments=segments,suggestions=suggestions,status='done')
    except Exception as exc:
        with lock:job.update(status='error',error=str(exc)[:900])

@app.get('/api/jobs/{jobid}')
def get_job(jobid:str):
    with lock:
        job=jobs.get(jobid)
        if not job:raise HTTPException(404,'Processo não encontrado (processos não persistem após reiniciar o servidor).')
        return public_job(job)

@app.post('/api/jobs/{jobid}/clips/{clipid}/render')
def clip_render(jobid:str,clipid:str,payload:RenderRequest):
    with lock:
        job=jobs.get(jobid)
        if not job:raise HTTPException(404,'Processo não encontrado.')
        if job['status']!='done':raise HTTPException(409,'Aguarde a conclusão da transcrição.')
        clip=next((x for x in job['suggestions'] if x['id']==clipid),None)
        if not clip:raise HTTPException(404,'Corte inexistente.')
        video=Path(job['file'])
        segments=list(job['segments'])
        clip=dict(clip)
        if payload.start is not None:clip['start']=payload.start
        if payload.end is not None:clip['end']=payload.end
    try:
        output=render_video(video,video.parent,segments,clip,payload.preset,title=payload.title)
    except Exception as exc:
        raise HTTPException(422,str(exc)[:700]) from exc
    return {'ok':True,'download_url':f'/api/jobs/{jobid}/download/{output.name}'}

@app.get('/api/jobs/{jobid}/download/{filename}')
def download(jobid:str,filename:str):
    if not re.fullmatch(r'[a-f0-9]{32}',jobid):raise HTTPException(404)
    if not re.fullmatch(r'clip-\d{2}\.mp4',filename):raise HTTPException(404)
    with lock:
        if jobid not in jobs:raise HTTPException(404)
    path=WORK/jobid/filename
    if not path.is_file():raise HTTPException(404)
    return FileResponse(path,media_type='video/mp4',filename=filename)

@app.get('/api/programs')
def list_programs():
    return json.loads((BASE/'docs'/'data'/'programs.json').read_text(encoding='utf-8'))

# IMPORTANTE: montar arquivos estáticos por último para não bloquear /api.
app.mount('/',StaticFiles(directory=str(BASE/'docs'),html=True),name='frontend')
