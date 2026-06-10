import os
from pynetdicom import AE, evt, debug_logger
from pydicom.dataset import Dataset
from sync_service import sync_dicom_to_mbm_lab

# Setup folders
RECEIVED_DIR = os.path.join(os.path.dirname(__file__), 'received')
os.makedirs(RECEIVED_DIR, exist_ok=True)

# debug_logger() # Uncomment for verbose pynetdicom logs

def handle_store(event):
    """Handle a C-STORE request event."""
    ds = event.dataset
    ds.file_meta = event.file_meta

    # Generate a unique filename
    filename = os.path.join(RECEIVED_DIR, f"{ds.SOPInstanceUID}.dcm")
    
    # Save the received DICOM dataset
    ds.save_as(filename, write_like_original=False)
    print(f"[*] Received and saved: {filename}")

    # Sync to Hipocrafy Lab
    sync_dicom_to_mbm_lab(ds)
    
    # Trigger Anonymization
    try:
        from anonymizer import anonymize_dicom
        anon_path = anonymize_dicom(filename)
        print(f"[*] Anonymized file created: {anon_path}")
    except ImportError:
        print("[!] Warning: anonymizer module not found.")
    
    return 0x0000 # Success status

def start_scp(port=11112):
    ae = AE(ae_title=b'HIPOCRAFY_GW')
    
    # Support all Storage Service Classes
    ae.add_supported_context('1.2.840.10008.5.1.4.1.1.6.1') # Ultrasound Image Storage
    ae.add_supported_context('1.2.840.10008.5.1.4.1.1.3.1') # Ultrasound Multi-frame Image Storage
    
    handlers = [(evt.EVT_C_STORE, handle_store)]
    
    print(f"[!] Hipocrafy Gateway SCP Listener starting on port {port}...")
    ae.start_server(('', port), block=True, evt_handlers=handlers)

if __name__ == "__main__":
    start_scp()
