import os
import sys

# Asegurar resolución de dependencias desde el virtualenv local y la raíz de hipocrafy-edge
_edge_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_site_packages = os.path.join(_edge_root, "venv", "Lib", "site-packages")
if os.path.exists(_site_packages) and _site_packages not in sys.path:
    sys.path.insert(0, _site_packages)
if _edge_root not in sys.path:
    sys.path.insert(0, _edge_root)

import unittest
import numpy as np
import pydicom
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, generate_uid
from dicom_anonymizer import anonymize_dicom_file, anonymize_pixel_data, _TAG_RULES

class TestDicomAnonymizerHardening(unittest.TestCase):
    
    def setUp(self):
        self.test_dir = os.path.join(os.path.dirname(__file__), "scratch_dicom")
        os.makedirs(self.test_dir, exist_ok=True)
        self.raw_dcm = os.path.join(self.test_dir, "test_input.dcm")
        self.anon_dcm = os.path.join(self.test_dir, "test_output_anon.dcm")

        # Crear un dataset DICOM sintético con datos PHI sensibles
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = '1.2.840.10008.5.1.4.1.1.7' # Secondary Capture
        file_meta.MediaStorageSOPInstanceUID = generate_uid()
        file_meta.TransferSyntaxUID = ExplicitVRLittleEndian

        ds = Dataset()
        ds.file_meta = file_meta
        ds.is_little_endian = True
        ds.is_implicit_VR = False

        # Datos PHI que NUNCA deben salir en texto claro hacia la nube
        ds.PatientName = "Perez^Juan^Carlos"
        ds.PatientID = "DNI-12345678"
        ds.PatientBirthDate = "19800515"
        ds.PatientSex = "M"
        ds.PatientAge = "046Y"
        ds.ReferringPhysicianName = "Dr. Gonzalez^Mario"
        ds.InstitutionName = "Hospital Privado Central"
        ds.StudyInstanceUID = generate_uid()
        ds.SeriesInstanceUID = generate_uid()
        ds.SOPInstanceUID = file_meta.MediaStorageSOPInstanceUID

        # Píxeles con texto sintético en la cabecera (burn-in text)
        pixels = np.zeros((100, 100), dtype=np.uint8)
        # Simular texto quemado en el top 10% (brillo 255)
        pixels[5:12, 10:90] = 255
        ds.PixelData = pixels.tobytes()
        ds.Rows, ds.Columns = 100, 100
        ds.BitsAllocated = 8
        ds.BitsStored = 8
        ds.HighBit = 7
        ds.PixelRepresentation = 0
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"

        ds.save_as(self.raw_dcm, write_like_original=False)

    def tearDown(self):
        # Limpieza de archivos temporales
        for f in [self.raw_dcm, self.anon_dcm]:
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass
        if os.path.exists(self.test_dir):
            try:
                os.rmdir(self.test_dir)
            except Exception:
                pass

    def test_phi_tags_are_thoroughly_scrubbed(self):
        """Valida que los tags de PHI (Protected Health Information) queden borrados o anonimizados."""
        result = anonymize_dicom_file(self.raw_dcm, self.anon_dcm)
        self.assertTrue(os.path.exists(result["output"]))

        anon_ds = pydicom.dcmread(self.anon_dcm)

        # 1. Nombre de paciente no debe contener el nombre real
        self.assertNotEqual(str(anon_ds.get("PatientName", "")), "Perez^Juan^Carlos")
        self.assertIn("ANONYMIZED", str(anon_ds.get("PatientName", "")))

        # 2. Fecha de nacimiento no debe existir o ser vacía
        birth_date = str(anon_ds.get("PatientBirthDate", ""))
        self.assertNotIn("19800515", birth_date)

        # 3. Médico derivante e institución deben estar ofuscados
        self.assertNotIn("Gonzalez", str(anon_ds.get("ReferringPhysicianName", "")))
        self.assertNotIn("Hospital Privado Central", str(anon_ds.get("InstitutionName", "")))

    def test_pixel_burn_in_masking(self):
        """Valida que el texto quemado en los píxeles superiores sea enmascarado a negro (0)."""
        pixels = np.zeros((100, 100), dtype=np.uint8)
        pixels[5:12, 10:90] = 255 # Texto brillante quemado en la cabecera

        masked = anonymize_pixel_data(pixels, bright_threshold=200, min_density=0.01)

        # La región con texto brillante debe haber sido reseteada a 0
        self.assertEqual(int(masked[5:12, 10:90].sum()), 0)

if __name__ == "__main__":
    unittest.main()
