const $=id=>document.getElementById(id);
const panels=["clips","ai","youtube","settings"];
document.querySelectorAll(".module").forEach(btn=>btn.addEventListener("click",()=>{
  document.querySelectorAll(".module").forEach(x=>x.classList.remove("active"));
  btn.classList.add("active"); panels.forEach(p=>$(p).classList.toggle("hidden",p!==btn.dataset.panel));
}));
$("settingsBtn").addEventListener("click",()=>{
  panels.forEach(p=>$(p).classList.toggle("hidden",p!=="settings"));
  document.querySelectorAll(".module").forEach(x=>x.classList.remove("active"));
});
let videoURL=null, selectedFile=null, exportURL=null, audioContext=null;
const source=$("sourceVideo"), preview=$("previewVideo");
$("videoInput").addEventListener("change",e=>{
  const file=e.target.files?.[0]; if(!file)return;
  if(!file.type.startsWith("video/")){setStatus("Selecciona un archivo de vídeo válido.");return;}
  if(videoURL)URL.revokeObjectURL(videoURL);
  if(exportURL)URL.revokeObjectURL(exportURL);
  selectedFile=file; videoURL=URL.createObjectURL(file);
  source.src=videoURL;preview.src=videoURL;
  $("fileName").textContent=`${file.name} · ${(file.size/1024/1024).toFixed(1)} MB`;
  $("editor").classList.remove("hidden");$("exportResult").classList.add("hidden");
  source.onloadedmetadata=()=>{
    $("endTime").value=Math.min(15,source.duration).toFixed(1);
    $("endTime").max=source.duration;
    setStatus(`Duración: ${source.duration.toFixed(1)} s. Archivo cargado localmente; no se ha subido a ningún servidor.`);
  };
});
$("hookText").addEventListener("input",()=>{$("hookOverlay").textContent=$("hookText").value||"Tu gancho aparecerá aquí";});
function setStatus(s){$("status").textContent=s;}
function getRange(){
 const start=Math.max(0,Number($("startTime").value)||0),end=Number($("endTime").value)||0;
 if(!selectedFile||!Number.isFinite(source.duration))throw Error("Primero selecciona un vídeo.");
 if(end<=start||start>=source.duration||end>source.duration+0.05)throw Error("Revisa el intervalo: el final debe ser mayor que el inicio y no superar la duración del vídeo.");
 if(end-start>90)throw Error("Para esta primera versión, limita cada exportación a 90 segundos para evitar problemas de memoria en iPhone.");
 return {start,end};
}
$("previewBtn").addEventListener("click",async()=>{
 try{const {start,end}=getRange();preview.currentTime=start;await preview.play();setStatus("Previsualizando el intervalo seleccionado…");
  const stop=()=>{if(preview.currentTime>=end){preview.pause();preview.removeEventListener("timeupdate",stop);setStatus("Previsualización terminada.");}};preview.addEventListener("timeupdate",stop);
 }catch(err){setStatus(err.message);}
});
function drawCover(ctx,video,w,h){
 const vw=video.videoWidth,vh=video.videoHeight;if(!vw||!vh)return;
 const scale=Math.max(w/vw,h/vh),sw=w/scale,sh=h/scale,sx=(vw-sw)/2,sy=(vh-sh)/2;
 ctx.drawImage(video,sx,sy,sw,sh,0,0,w,h);
 const hook=$("hookText").value.trim();if(hook){
  const fontSize=Math.max(34,Math.min(58,Math.round(w*0.065)));ctx.font=`900 ${fontSize}px -apple-system,Arial,sans-serif`;
  const words=hook.split(/\s+/),lines=[];let line="";
  for(const word of words){const test=line?line+" "+word:word;if(ctx.measureText(test).width>w-90&&line){lines.push(line);line=word;}else line=test;}if(line)lines.push(line);
  const lineH=fontSize*1.18,boxH=lines.length*lineH+42,y=h*.68;
  ctx.fillStyle="rgba(0,0,0,.62)";ctx.fillRect(28,y-20,w-56,boxH);
  ctx.fillStyle="#fff";ctx.textAlign="center";ctx.textBaseline="top";lines.forEach((t,i)=>ctx.fillText(t,w/2,y+i*lineH));
 }
}
async function exportClip(){
 const {start,end}=getRange();
 if(!window.MediaRecorder||!HTMLCanvasElement.prototype.captureStream)throw Error("Este navegador no dispone de las funciones necesarias para exportar. Abre la app en Safari actualizado.");
 const canvas=document.createElement("canvas");canvas.width=720;canvas.height=1280;const ctx=canvas.getContext("2d");
 const stream=canvas.captureStream(30);let audioTrack=null,sourceNode=null,destination=null;
 try{
  const AC=window.AudioContext||window.webkitAudioContext;
  if(AC){
   if(!audioContext){audioContext=new AC();sourceNode=audioContext.createMediaElementSource(source);sourceNode.connect(audioContext.destination);}
   await audioContext.resume();destination=audioContext.createMediaStreamDestination();sourceNode.connect(destination);
   audioTrack=destination.stream.getAudioTracks()[0];if(audioTrack)stream.addTrack(audioTrack);
  }
 }catch(e){console.warn("Audio capture unavailable",e);}
 const candidates=['video/mp4;codecs="avc1.42E01E,mp4a.40.2"','video/mp4','video/webm;codecs=vp9,opus','video/webm'];
 const mime=candidates.find(t=>MediaRecorder.isTypeSupported(t));if(!mime)throw Error("Safari no informa de un formato de grabación compatible en este dispositivo.");
 const recorder=new MediaRecorder(stream,{mimeType:mime,videoBitsPerSecond:4500000});const chunks=[];
 recorder.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data);};
 const done=new Promise((resolve,reject)=>{recorder.onstop=resolve;recorder.onerror=()=>reject(Error("Falló la grabación del vídeo."));});
 source.pause();source.currentTime=start;await new Promise((resolve,reject)=>{source.onseeked=resolve;source.onerror=()=>reject(Error("No se pudo posicionar el vídeo."));});
 const frame=()=>{if(source.readyState>=2)drawCover(ctx,source,canvas.width,canvas.height);};
 frame();recorder.start(500);await source.play();setStatus("Exportando en el iPhone… no cierres Safari ni bloquees la pantalla.");
 const duration=end-start;let rafId;let stopped=false;
 const tick=()=>{if(stopped)return;frame();const pct=Math.min(100,((source.currentTime-start)/duration)*100);$("progressBar").style.width=pct+"%";if(source.currentTime>=end){stopped=true;source.pause();recorder.stop();cancelAnimationFrame(rafId);}else rafId=requestAnimationFrame(tick);};
 rafId=requestAnimationFrame(tick);
 await done;stream.getTracks().forEach(t=>t.stop());if(destination&&sourceNode){try{sourceNode.disconnect(destination);}catch(e){}}
 const actualMime=recorder.mimeType||mime;const blob=new Blob(chunks,{type:actualMime});if(!blob.size)throw Error("El archivo exportado está vacío.");
 if(exportURL)URL.revokeObjectURL(exportURL);exportURL=URL.createObjectURL(blob);
 const ext=actualMime.includes("mp4")?"mp4":"webm";const name=`openshorts-${Date.now()}.${ext}`;
 const result=$("exportResult");result.classList.remove("hidden");result.innerHTML=`<b>Exportación terminada</b><br>${(blob.size/1024/1024).toFixed(1)} MB · ${ext.toUpperCase()} · 720 × 1280<br><a id="downloadClip" href="${exportURL}" download="${name}">Guardar vídeo exportado</a><br><small>Si Safari no descarga directamente, mantén pulsado el enlace y elige compartir o guardar en Archivos.</small>`;
 $("downloadClip").addEventListener("click",()=>setTimeout(()=>setStatus("Si no aparece la descarga, utiliza el menú Compartir de Safari para guardar el archivo."),800));
 $("progressBar").style.width="100%";setStatus("Exportación completada. Comprueba el archivo guardado antes de eliminar el vídeo original.");
}
$("exportBtn").addEventListener("click",async()=>{
 $("exportBtn").disabled=true;$("progressBar").style.width="0%";$("exportResult").classList.add("hidden");
 try{await exportClip();}catch(err){setStatus(err.message||"No se pudo exportar el vídeo.");}finally{$("exportBtn").disabled=false;}
});
if("serviceWorker" in navigator && location.protocol.startsWith("http"))navigator.serviceWorker.register("./sw.js").catch(()=>{});
