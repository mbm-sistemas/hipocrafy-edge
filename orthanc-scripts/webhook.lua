function OnStableStudy(studyId, tags, metadata)
   -- Triggered when a DICOM study has finished receiving all instances
   -- and no new instance has arrived for 'StableAge' seconds.
   --
   -- IMPORTANTE: la ruta y el payload acá DEBEN coincidir exactamente con lo
   -- que espera @app.post("/orthanc-webhook") en main.py (data.get("ID")).
   -- Antes este script apuntaba a una ruta y una clave distintas y nunca
   -- llegaba a ejecutarse nada del lado de FastAPI — el procesamiento de
   -- estudios dependía solo del polling cada 10s (poll_orthanc), nunca de
   -- este webhook.
   print("Stable study arrived: " .. studyId)

   local payload = {}
   payload["ID"] = studyId

   local headers = {}
   headers["Content-Type"] = "application/json"

   -- Docker Desktop network trick to reach the host's localhost where FastAPI runs
   local url = "http://host.docker.internal:8080/orthanc-webhook"

   local result = HttpPost(url, DumpJson(payload), headers)
   print("Webhook triggered, result: " .. result)
end
