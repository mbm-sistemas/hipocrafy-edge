function OnStableStudy(studyId, tags, metadata)
   -- Triggered when a DICOM study has finished receiving all instances
   -- and no new instance has arrived for 'StableAge' seconds.
   print("Stable study arrived: " .. studyId)
   
   local payload = {}
   payload["orthanc_study_id"] = studyId
   payload["patient_id"] = tags["PatientID"] or "UNKNOWN"
   
   local headers = {}
   headers["Content-Type"] = "application/json"
   
   -- Docker Desktop network trick to reach the host's localhost where FastAPI runs
   local url = "http://host.docker.internal:8080/webhook/orthanc-new-study"
   
   local result = HttpPost(url, DumpJson(payload), headers)
   print("Webhook triggered, result: " .. result)
end
