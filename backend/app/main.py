import json, os, subprocess, tempfile
from pathlib import Path
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import httpx
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel

VERSION = "0.9.0"
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "100"))
ALLOWED_MODELS = {"tiny", "base"}
executor = ThreadPoolExecutor(max_workers=1)
app = FastAPI(title="OpenShorts AI Studio", version=VERSION)

origins = [x.strip() for x in os.getenv("ALLOWED_ORIGINS", "").split(",") if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins or ["*"], allow_credentials=False,
                   allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

@lru_cache(maxsize=1)
def get_model(name: str):
    return WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=2, num_workers=1)

@app.get("/")
def root():
    return {"service":"OpenShorts AI Studio","status":"ok","version":VERSION,"docs":"/docs"}

@app.get("/health")
def health():
    return {"status":"ok","version":VERSION,"gemini_configured":bool(os.getenv("GEMINI_API_KEY")),
            "whisper_default":os.getenv("WHISPER_MODEL","tiny"),"max_upload_mb":MAX_UPLOAD_MB}

async def gemini(prompt: str):
    key=os.getenv("GEMINI_API_KEY")
    if not key:
        raise HTTPException(503,"Falta configurar GEMINI_API_KEY en las variables de entorno de Render.")
    model=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0,connect=15.0)) as client:
            r=await client.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                params={"key":key},json={"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"responseMimeType":"application/json","temperature":0.2}})
    except httpx.TimeoutException:
        raise HTTPException(504,"Gemini ha tardado demasiado en responder. Inténtalo de nuevo.")
    except httpx.HTTPError as e:
        raise HTTPException(502,f"No se pudo conectar con Gemini: {type(e).__name__}.")
    if r.status_code>=400:
        try: detail=r.json().get("error",{}).get("message","Gemini rechazó la solicitud.")
        except Exception: detail="Gemini rechazó la solicitud."
        raise HTTPException(502,detail[:500])
    try: return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
    except Exception: raise HTTPException(502,"Gemini devolvió una respuesta vacía o JSON no válido.")

@app.post("/api/analyze-video")
async def analyze_video(video:UploadFile=File(...), niche:str=Form("auto"), country:str=Form("España"),
    goal:str=Form("Alcance y retención"), max_clips:int=Form(5), min_duration:int=Form(20),
    max_duration:int=Form(60), face_tracking:str=Form("center"), whisper_model:str=Form("tiny"),
    subtitle_language:str=Form("es"), subtitle_preset:str=Form("viral"), resolution:str=Form("1080p"),
    aspect_ratio:str=Form("9:16"), output_folder:str=Form("OpenShorts/Exports"),
    delete_source:bool=Form(False), watermark_position:str=Form("bottom-right"),
    watermark_size:int=Form(15), watermark:UploadFile|None=File(None)):
    if not video.filename: raise HTTPException(400,"El vídeo no tiene nombre de archivo.")
    if min_duration<5 or max_duration<min_duration or max_duration>180:
        raise HTTPException(422,"Rango de duración no válido.")
    max_clips=max(1,min(max_clips,8))
    model_name=whisper_model if whisper_model in ALLOWED_MODELS else os.getenv("WHISPER_MODEL","tiny")
    if model_name not in ALLOWED_MODELS: model_name="tiny"
    suffix=Path(video.filename).suffix.lower() or ".mp4"
    if suffix not in {".mp4",".mov",".m4v",".webm",".mkv",".avi"}:
        raise HTTPException(415,"Formato no admitido. Usa MP4, MOV, M4V, WebM, MKV o AVI.")
    with tempfile.TemporaryDirectory(prefix="openshorts_") as td:
        source=Path(td)/("source"+suffix); total=0
        try:
            with source.open("wb") as f:
                while True:
                    chunk=await video.read(1024*1024)
                    if not chunk: break
                    total+=len(chunk)
                    if total>MAX_UPLOAD_MB*1024*1024:
                        raise HTTPException(413,f"El vídeo supera el límite de {MAX_UPLOAD_MB} MB.")
                    f.write(chunk)
        finally: await video.close()
        if not total: raise HTTPException(400,"El archivo está vacío.")
        audio=Path(td)/"audio.wav"
        try:
            proc=subprocess.run(["ffmpeg","-nostdin","-y","-i",str(source),"-vn","-ac","1","-ar","16000",
                "-acodec","pcm_s16le",str(audio)],capture_output=True,text=True,timeout=180)
        except subprocess.TimeoutExpired: raise HTTPException(504,"FFmpeg ha tardado demasiado extrayendo el audio.")
        if proc.returncode or not audio.exists() or not audio.stat().st_size:
            raise HTTPException(422,"No se pudo extraer el audio. Comprueba que el vídeo contiene audio y es compatible.")
        try:
            model=get_model(model_name)
            future=executor.submit(lambda:model.transcribe(str(audio),beam_size=1,vad_filter=True,
                condition_on_previous_text=False))
            segments,info=future.result(timeout=240)
            lines=[{"start":round(s.start,2),"end":round(s.end,2),"text":s.text.strip()}
                   for s in segments if s.text.strip()]
        except TimeoutError: raise HTTPException(504,"La transcripción ha superado el límite de tiempo.")
        except Exception as e: raise HTTPException(503,f"No se pudo ejecutar Whisper ({type(e).__name__}). Usa tiny en Render Free.")
        if not lines: raise HTTPException(422,"No se detectó voz en el vídeo.")
        transcript="\\n".join(f'[{x["start"]}-{x["end"]}] {x["text"]}' for x in lines)
        prompt=f"""Analiza esta transcripción temporizada. Nicho: {niche}. País: {country}. Objetivo: {goal}.
Propón como máximo {max_clips} clips completos, cada uno con gancho, desarrollo y cierre.
Duración objetivo {min_duration}-{max_duration} segundos. No inventes palabras ni tiempos.
El vídeo dura {info.duration:.2f} segundos. Devuelve SOLO JSON:
{{"clips":[{{"title":"...","start":0,"end":30,"hook":"...","closing":"...","reason":"...","subtitles":[{{"start":0,"text":"..."}}],"rubric":{{"hook":0,"retention":0,"clarity":0,"emotion":0,"shareability":0,"closing":0}},"evidence":"...","confidence":"alta|media|baja"}}]}}
Rubric 0-5. No afirmes viralidad real. Transcripción:\\n{transcript[:65000]}"""
        result=await gemini(prompt)
        raw=result.get("clips",[])
        if not isinstance(raw,list): raise HTTPException(502,"Gemini no devolvió una lista de clips.")
        weights={"hook":20,"retention":20,"clarity":15,"emotion":15,"shareability":15,"closing":15}
        clips=[]
        for c in raw[:max_clips]:
            try: start=max(0,float(c.get("start",0))); end=min(float(info.duration),float(c.get("end",0)))
            except (TypeError,ValueError): continue
            if end<=start: continue
            rubric=c.get("rubric") or {}; score=0
            for k,w in weights.items():
                try: score+=max(0,min(5,float(rubric.get(k,0))))/5*w
                except (TypeError,ValueError): pass
            c.update({"start":round(start,2),"end":round(end,2),"duration":round(end-start,2),
                "editorial_score":round(score),"viral_score":None,
                "score_type":"Puntuación editorial orientativa; no es viralidad verificada."})
            clips.append(c)
        if not clips: raise HTTPException(502,"Gemini no encontró clips válidos.")
        return {"status":"analyzed","version":VERSION,"duration":round(info.duration,2),"language":info.language,
            "transcript_segments":lines,"clips":clips,
            "production_settings_received":{"face_tracking":face_tracking,"subtitle_language":subtitle_language,
            "subtitle_preset":subtitle_preset,"resolution":resolution,"aspect_ratio":aspect_ratio,
            "output_folder":output_folder,"delete_source":delete_source,"watermark_position":watermark_position,
            "watermark_size":watermark_size,"watermark_received":bool(watermark),"whisper_model_used":model_name},
            "notice":"Análisis completado. Esta versión propone clips; todavía no genera MP4 ni aplica tracking facial, marca de agua o subtítulos quemados."}
