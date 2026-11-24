import os,json,tempfile,subprocess
from pathlib import Path
import httpx
from fastapi import FastAPI,UploadFile,File,Form,HTTPException
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel
app=FastAPI(title="OpenShorts AI Studio",version="0.6")
origins=[x.strip() for x in os.getenv("ALLOWED_ORIGINS","").split(",") if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=origins or ["*"],allow_methods=["GET","POST"],allow_headers=["*"])
model=None
@app.get("/health")
def health(): return {"status":"ok","version":"0.6"}
async def gemini(prompt):
 key=os.getenv("GEMINI_API_KEY")
 if not key: raise HTTPException(503,"Configura GEMINI_API_KEY en el servidor.")
 name=os.getenv("GEMINI_MODEL","gemini-2.5-flash")
 async with httpx.AsyncClient(timeout=180) as c:
  r=await c.post(f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent?key={key}",json={"contents":[{"parts":[{"text":prompt}]}],"generationConfig":{"responseMimeType":"application/json","temperature":0.2}})
 if r.status_code>=400: raise HTTPException(502,r.text[:300])
 try:return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
 except Exception:raise HTTPException(502,"Gemini devolvió una respuesta no válida.")
@app.post("/api/analyze-video")
async def analyze_video(video:UploadFile=File(...),niche:str=Form("auto"),country:str=Form("España"),goal:str=Form("Alcance y retención"),max_clips:int=Form(5),min_duration:int=Form(20),max_duration:int=Form(60),face_tracking:str=Form("face"),whisper_model:str=Form("small"),subtitle_language:str=Form("es"),subtitle_preset:str=Form("viral"),resolution:str=Form("1080p"),aspect_ratio:str=Form("9:16"),output_folder:str=Form("OpenShorts/Exports"),delete_source:bool=Form(True),watermark_position:str=Form("bottom-right"),watermark_size:int=Form(15),watermark:UploadFile|None=File(None)):
 global model
 data=await video.read()
 if len(data)>int(os.getenv("MAX_UPLOAD_MB","1500"))*1024*1024:raise HTTPException(413,"Vídeo demasiado grande.")
 with tempfile.TemporaryDirectory() as td:
  src=str(Path(td)/("source"+(Path(video.filename or "v.mp4").suffix or ".mp4")));aud=str(Path(td)/"audio.wav");Path(src).write_bytes(data)
  p=subprocess.run(["ffmpeg","-y","-i",src,"-vn","-ac","1","-ar","16000",aud],capture_output=True)
  if p.returncode:raise HTTPException(422,"No se pudo extraer audio.")
  if model is None:model=WhisperModel(os.getenv("WHISPER_MODEL","small"),device="cpu",compute_type="int8")
  segments,info=model.transcribe(aud,beam_size=5,vad_filter=True)
  lines=[{"start":round(s.start,2),"end":round(s.end,2),"text":s.text.strip()} for s in segments]
  transcript="\n".join(f'[{x["start"]}-{x["end"]}] {x["text"]}' for x in lines)
  prompt=f"""Analiza esta transcripción temporizada de un vídeo. Nicho {niche}, país {country}, objetivo {goal}. Propón entre 4 y {max_clips} clips completos, duración objetivo entre {min_duration} y {max_duration} segundos, cada uno con gancho, desarrollo y cierre/payoff. No recortes por duración arbitraria. No inventes palabras ni tiempos. Devuelve JSON {{ "clips":[...] }} con title,start,end,hook,closing,reason,subtitles:[{{start,text}}],rubric:{{hook,retention,clarity,emotion,shareability,closing}}, evidence, confidence. Notas rubric 0-5. No afirmes viralidad verificada sin métricas de publicaciones reales; deja viral_score null. Máximo {max_clips}. Transcripción:\n{transcript[:90000]}"""
  out=await gemini(prompt);clips=out.get("clips",[])[:5]
  weights={"hook":20,"retention":20,"clarity":15,"emotion":15,"shareability":15,"closing":15}
  for c in clips:
   rubric=c.get("rubric",{})
   c["editorial_score"]=round(sum(max(0,min(5,float(rubric.get(k,0))))/5*w for k,w in weights.items()))
   c["viral_score"]=None
   c["score_type"]="Puntuación editorial orientativa, no verificada con resultados de publicaciones"
  return {"status":"analyzed","duration":info.duration,"language":info.language,"clips":clips,"production_settings":{"face_tracking":face_tracking,"subtitle_language":subtitle_language,"subtitle_preset":subtitle_preset,"resolution":resolution,"aspect_ratio":aspect_ratio,"output_folder":output_folder,"delete_source":delete_source,"watermark_position":watermark_position,"watermark_size":watermark_size,"watermark_received":bool(watermark)},"notice":"La puntuación editorial no equivale a probabilidad de viralidad. La verificación requiere métricas reales de retención, compartidos y rendimiento."}
