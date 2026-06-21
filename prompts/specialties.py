import json
import os

"""
Sistema de Prompts Médicos por Especialidad.

Cada especialidad define:
- focus_areas: qué estructuras/órganos priorizar
- pathology_signs: signos patológicos específicos a buscar
- measurements: mediciones clínicas relevantes
- red_flags: hallazgos que requieren acción inmediata
"""

SPECIALTY_PROMPTS = {
    "ginecologia": {
        "display_name": "Ginecología y Obstetricia",
        "focus_areas": [
            "Útero (forma, tamaño, ecoestructura del miometrio)",
            "Endometrio (espesor, homogeneidad, línea endometrial)",
            "Ovarios (volumen, folículos, presencia de masas sólidas o quísticas)",
            "Fondo de saco de Douglas (líquido libre)",
            "Trompas de Falopio (si son visibles, dilatación)"
        ],
        "pathology_signs": [
            "Quistes ováricos (simples, complejos, hemorrágicos, dermoides)",
            "Miomas uterinos (submucosos, intramurales, subserosos) — medir tamaño y ubicación",
            "Endometriosis (endometriomas 'chocolate', nódulos en tabique rectovaginal)",
            "Embarazo ectópico (masa anexial con anillo tubárico, líquido libre)",
            "Poliposis endometrial (engrosamiento focal del endometrio)",
            "Síndrome de ovario poliquístico (>12 folículos periféricos, volumen ovárico >10cc)"
        ],
        "measurements": [
            "Espesor endometrial en mm (normal: <14mm premenopausia, <5mm postmenopausia)",
            "Dimensiones uterinas (longitudinal, anteroposterior, transverso)",
            "Volumen ovárico (largo x ancho x alto x 0.523)",
            "Tamaño de masas o quistes en sus 3 ejes"
        ],
        "red_flags": [
            "Masa sólida ovárica con flujo Doppler interno",
            "Líquido libre en fondo de saco con β-hCG positiva (descartar ectópico)",
            "Endometrio >5mm en paciente postmenopáusica con sangrado"
        ],
        "organ_measurements_schema": {
            "utero": {
                "longitud_mm": None,
                "ap_mm": None,
                "transverso_mm": None,
                "endometrio_mm": None
            },
            "ovario_izquierdo": {
                "longitud_mm": None,
                "ancho_mm": None,
                "alto_mm": None,
                "volumen_cc": None,
                "n_foliculos": None,
                "foliculo_mayor_mm": None
            },
            "ovario_derecho": {
                "longitud_mm": None,
                "ancho_mm": None,
                "alto_mm": None,
                "volumen_cc": None,
                "n_foliculos": None,
                "foliculo_mayor_mm": None
            },
            "douglas": {
                "liquido_libre_ml": None
            },
            "masa_anexial": {
                "dim1_mm": None,
                "dim2_mm": None,
                "dim3_mm": None
            }
        }
    },

    "traumatologia": {
        "display_name": "Traumatología y Ortopedia",
        "focus_areas": [
            "Cortical ósea (continuidad, irregularidades)",
            "Espacio articular (simetría, pinzamiento)",
            "Tejidos blandos periarticulares (edema, colecciones)",
            "Alineación ósea y ejes mecánicos",
            "Dispositivos de osteosíntesis (si presentes, posición y estado)"
        ],
        "pathology_signs": [
            "Fracturas (trazo, desplazamiento, conminución, compromiso articular)",
            "Luxaciones (pérdida de congruencia articular)",
            "Artrosis (osteofitos, pinzamiento del espacio articular, esclerosis subcondral)",
            "Osteomielitis (destrucción cortical, reacción perióstica, secuestros)",
            "Lesiones ligamentarias (ensanchamiento del espacio articular bajo estrés)",
            "Tumores óseos (lesiones líticas u osteoblásticas, reacción perióstica en 'sol naciente')"
        ],
        "measurements": [
            "Ángulo de Böhler (calcáneo, normal: 25-40°)",
            "Espacio articular en mm",
            "Desplazamiento de fragmentos en mm",
            "Ángulo de inclinación (cadera)"
        ],
        "red_flags": [
            "Fractura expuesta o con compromiso vascular",
            "Luxación articular no reducida",
            "Lesión lítica con bordes irregulares y destrucción cortical (sospecha tumoral)",
            "Fractura de columna con compromiso del canal medular"
        ]
    },

    "cardiologia": {
        "display_name": "Cardiología",
        "focus_areas": [
            "Silueta cardíaca (tamaño, índice cardiotorácico)",
            "Cavidades cardíacas (dilatación auricular o ventricular)",
            "Válvulas (engrosamiento, calcificación, prolapso)",
            "Pericardio (engrosamiento, derrame)",
            "Grandes vasos (aorta, arteria pulmonar)"
        ],
        "pathology_signs": [
            "Cardiomegalia (índice cardiotorácico >0.5)",
            "Derrame pericárdico (separación de hojas pericárdicas)",
            "Insuficiencia cardíaca (redistribución vascular pulmonar, líneas de Kerley)",
            "Calcificación valvular (aórtica, mitral)",
            "Aneurisma de aorta torácica (diámetro >4cm)",
            "Edema pulmonar (opacidades bilaterales en 'alas de mariposa')"
        ],
        "measurements": [
            "Índice cardiotorácico (normal: <0.5)",
            "Diámetro de la aorta ascendente en mm",
            "Fracción de eyección (si ecocardiograma)",
            "Grosor del septum interventricular"
        ],
        "red_flags": [
            "Derrame pericárdico masivo con signos de taponamiento",
            "Disección aórtica (doble luz, flap intimal)",
            "Edema agudo de pulmón"
        ]
    },

    "neumonologia": {
        "display_name": "Neumonología / Neumología",
        "focus_areas": [
            "Parénquima pulmonar (campos pulmonares, simetría)",
            "Mediastino (ancho, masas, adenopatías)",
            "Pleura (engrosamiento, derrames)",
            "Diafragma (posición, movilidad)",
            "Tráquea y bronquios principales"
        ],
        "pathology_signs": [
            "Neumonía (consolidación lobar, broncograma aéreo, opacidades en vidrio esmerilado)",
            "Derrame pleural (opacificación del seno costofrénico, menisco)",
            "Neumotórax (ausencia de trama vascular, línea pleural visible)",
            "Nódulo pulmonar (solitario: evaluar bordes, tamaño, calcificación)",
            "EPOC (hiperinsuflación, aplanamiento diafragmático, bullas)",
            "Fibrosis pulmonar (patrón reticular, panalización basal)"
        ],
        "measurements": [
            "Tamaño de nódulos pulmonares en mm",
            "Estimación del volumen de derrame pleural",
            "Ancho del mediastino"
        ],
        "red_flags": [
            "Neumotórax a tensión (desviación mediastínica contralateral)",
            "Nódulo pulmonar >8mm sin calcificación (sospecha neoplásica)",
            "TEP: oligohemia focal, signo de Westermark"
        ]
    },

    "gastroenterologia": {
        "display_name": "Gastroenterología / Abdomen",
        "focus_areas": [
            "Hígado (tamaño, ecoestructura, bordes)",
            "Vesícula biliar (pared, contenido, vía biliar)",
            "Páncreas (tamaño, contornos, conducto de Wirsung)",
            "Bazo (tamaño, ecoestructura)",
            "Riñones (tamaño, corteza, sistema pielocalicial)",
            "Asas intestinales (dilatación, peristaltismo)",
            "Aorta abdominal y espacios retroperitoneales"
        ],
        "pathology_signs": [
            "Esteatosis hepática (hígado hiperecogénico, atenuación posterior)",
            "Litiasis vesicular (imágenes hiperecogénicas con sombra acústica posterior)",
            "Colecistitis (pared vesicular >4mm, Murphy ecográfico positivo, líquido perivesicular)",
            "Pancreatitis (aumento de tamaño, bordes irregulares, colecciones peripancreáticas)",
            "Hidronefrosis (dilatación del sistema pielocalicial)",
            "Ascitis (líquido libre en espacios declives)"
        ],
        "measurements": [
            "Diámetro longitudinal hepático (normal: <15cm en línea medioclavicular)",
            "Espesor de pared vesicular (normal: <4mm)",
            "Diámetro del colédoco (normal: <7mm, post-colecistectomía: <10mm)",
            "Diámetro del conducto de Wirsung (normal: <3mm)",
            "Longitud renal (normal: 10-12cm)",
            "Diámetro de aorta abdominal (normal: <3cm)"
        ],
        "red_flags": [
            "Masa hepática sólida hipervascularizada (sospecha de hepatocarcinoma)",
            "Dilatación de la vía biliar con masa en cabeza de páncreas",
            "Aneurisma de aorta abdominal >5.5cm (riesgo de ruptura)",
            "Líquido libre + defensa abdominal (abdomen agudo)"
        ]
    },

    "pediatria": {
        "display_name": "Pediatría",
        "focus_areas": [
            "Proporciones corporales según edad gestacional/cronológica",
            "Fontanelas y suturas (si ecografía transfontanelar)",
            "Timo (tamaño normal en lactantes, no confundir con masa mediastínica)",
            "Caderas (ángulo alfa/beta en displasia)",
            "Abdomen pediátrico (hígado, riñones, vejiga)"
        ],
        "pathology_signs": [
            "Estenosis hipertrófica del píloro (grosor muscular >3mm, longitud >15mm)",
            "Invaginación intestinal (signo de 'diana' o 'donut')",
            "Displasia de cadera (ángulo alfa <60°)",
            "Hemorragia intraventricular (en prematuros)",
            "Neumonía atípica del lactante"
        ],
        "measurements": [
            "Ángulo alfa de cadera (normal: >60°)",
            "Grosor del músculo pilórico",
            "Perímetro cefálico vs. edad"
        ],
        "red_flags": [
            "Hemorragia intraventricular grado III-IV en prematuro",
            "Masa abdominal en niño (descartar neuroblastoma, tumor de Wilms)",
            "Invaginación intestinal no resuelta (isquemia intestinal)"
        ]
    },

    "oftalmologia": {
        "display_name": "Oftalmología",
        "focus_areas": ["Globo ocular (forma, ecoestructura)", "Cristalino (opacidades)", "Retina (desprendimiento)", "Humor vítreo (opacidades, hemorragias)", "Nervio óptico (excavación)"],
        "pathology_signs": ["Desprendimiento de retina (membrana flotante)", "Hemorragia vítrea", "Catarata (opacidad del cristalino)", "Glaucoma (excavación papilar >0.6)", "Melanoma coroideo (masa sólida ecogénica)", "Cuerpo extraño intraocular"],
        "measurements": ["Longitud axial del globo ocular (normal: 22-24mm)", "Excavación papilar (cup/disc ratio)", "Presión intraocular estimada"],
        "red_flags": ["Desprendimiento de retina agudo", "Cuerpo extraño intraocular metálico", "Masa intraocular sólida vascularizada"]
    },

    "neurologia": {
        "display_name": "Neurología / Neurocirugía",
        "focus_areas": ["Parénquima cerebral (simetría, densidad)", "Sistema ventricular (tamaño, simetría)", "Espacios subaracnoideos", "Fosa posterior (cerebelo, tronco)", "Columna vertebral y canal medular"],
        "pathology_signs": ["ACV isquémico (hipodensidad territorial, signo de la arteria cerebral media)", "Hemorragia intraparenquimatosa", "Hidrocefalia (dilatación ventricular)", "Hernias cerebrales (desplazamiento de línea media)", "Tumores (efecto de masa, edema perilesional)", "Hemorragia subaracnoidea (hiperdensidad cisternal)"],
        "measurements": ["Desplazamiento de línea media en mm (normal: 0mm)", "Diámetro de ventrículos laterales", "Tamaño de lesiones ocupantes de espacio"],
        "red_flags": ["Desplazamiento de línea media >5mm", "Hemorragia subaracnoidea (Fisher III-IV)", "Hernia uncal o transtentorial", "Hidrocefalia aguda obstructiva"]
    },

    "urologia": {
        "display_name": "Urología",
        "focus_areas": ["Riñones (tamaño, corteza, diferenciación corticomedular)", "Vías urinarias (uréteres, pelvis renal)", "Vejiga (pared, contenido, volumen residual)", "Próstata (tamaño, ecoestructura, zonas)", "Testículos (ecoestructura, flujo Doppler)"],
        "pathology_signs": ["Litiasis renal/ureteral (imagen hiperecogénica con sombra)", "Hidronefrosis (dilatación pielocalicial)", "Hiperplasia prostática benigna (volumen >30cc)", "Masa renal sólida (descartar carcinoma)", "Torsión testicular (ausencia de flujo Doppler)", "Varicocele (dilatación del plexo pampiniforme >3mm)"],
        "measurements": ["Longitud renal bilateral (normal: 10-12cm)", "Volumen prostático (L x A x H x 0.523)", "Volumen residual post-miccional (normal: <50ml)", "Diámetro ureteral (normal: <5mm)"],
        "red_flags": ["Torsión testicular (ausencia de flujo, emergencia quirúrgica)", "Masa renal sólida con neovascularización", "Uropatía obstructiva bilateral con falla renal", "Rotura renal traumática"]
    },

    "dermatologia": {
        "display_name": "Dermatología (Dermatoscopía/Ecografía cutánea)",
        "focus_areas": ["Epidermis y dermis (espesor, ecogenicidad)", "Hipodermis (nódulos, colecciones)", "Lesiones pigmentadas (bordes, simetría, vascularización)", "Ganglios linfáticos regionales"],
        "pathology_signs": ["Melanoma (asimetría, bordes irregulares, vascularización interna)", "Carcinoma basocelular (nódulo hipoecoico con vasos)", "Lipoma (masa homogénea hiperecoica)", "Absceso cutáneo (colección con contenido heterogéneo)", "Quiste epidérmico (masa anecoica bien delimitada)"],
        "measurements": ["Espesor de la lesión (Breslow en melanoma)", "Dimensiones de la lesión en 3 ejes", "Distancia a plano profundo"],
        "red_flags": ["Lesión pigmentada asimétrica con vascularización central", "Ganglio linfático regional con pérdida de hilio graso", "Crecimiento rápido documentado"]
    },

    "endocrinologia": {
        "display_name": "Endocrinología",
        "focus_areas": ["Tiroides (tamaño, ecoestructura, nódulos)", "Paratiroides (adenomas)", "Glándulas suprarrenales (masas)", "Páncreas endocrino"],
        "pathology_signs": ["Nódulo tiroideo sólido (evaluar TI-RADS: microcalcificaciones, bordes irregulares, más alto que ancho)", "Bocio multinodular", "Tiroiditis de Hashimoto (ecoestructura heterogénea, hipoecoica)", "Adenoma paratiroideo (nódulo hipoecoico posterior a tiroides)", "Incidentaloma suprarrenal"],
        "measurements": ["Volumen tiroideo por lóbulo (normal: <18ml mujeres, <25ml hombres)", "Tamaño del nódulo dominante en 3 ejes", "Clasificación TI-RADS del nódulo"],
        "red_flags": ["Nódulo TI-RADS 5 (alta sospecha de malignidad)", "Nódulo con invasión extratiroidea", "Adenoma suprarrenal >4cm (descartar carcinoma)"]
    },

    "otorrinolaringologia": {
        "display_name": "Otorrinolaringología (ORL)",
        "focus_areas": ["Glándulas salivales (parótidas, submandibulares)", "Cadenas ganglionares cervicales", "Senos paranasales", "Laringe y cuerdas vocales", "Oído medio (si TC)"],
        "pathology_signs": ["Sinusitis (opacificación de senos, nivel hidroaéreo)", "Adenopatía cervical patológica (redondeada, sin hilio graso, >1cm)", "Sialolitiasis (cálculo en conducto salival)", "Masa parotídea (tumor mixto, adenoma pleomorfo)", "Colesteatoma (masa en oído medio con erosión ósea)"],
        "measurements": ["Tamaño ganglionar (eje corto >10mm = patológico)", "Dimensiones de masas en glándulas salivales", "Grado de obstrucción sinusal"],
        "red_flags": ["Masa cervical sólida con necrosis central (sospecha metastásica)", "Parálisis de cuerda vocal con masa mediastínica", "Absceso periamigdalino"]
    },

    "reumatologia": {
        "display_name": "Reumatología",
        "focus_areas": ["Articulaciones (sinovial, cartílago, espacio articular)", "Tendones y entesis (inserciones)", "Tejido subcutáneo (nódulos, tofos)", "Erosiones óseas periarticulares"],
        "pathology_signs": ["Sinovitis (engrosamiento sinovial con señal Doppler)", "Erosiones óseas marginales (artritis reumatoide)", "Tofos gotosos (depósitos hiperecogénicos con doble contorno)", "Tenosinovitis (líquido peritendinoso)", "Entesopatía (engrosamiento e hipoecogenicidad de la entesis)", "Bursitis (distensión de bursa con líquido)"],
        "measurements": ["Espesor sinovial en mm", "Tamaño de erosiones óseas", "Señal Doppler (grado 0-3)"],
        "red_flags": ["Sinovitis activa con señal Doppler grado 3", "Erosión ósea progresiva", "Rotura tendinosa"]
    },

    "cirugia_vascular": {
        "display_name": "Cirugía Vascular",
        "focus_areas": ["Arterias carótidas (íntima-media, placas)", "Aorta (diámetro, aneurismas)", "Arterias de miembros inferiores (permeabilidad)", "Venas de miembros inferiores (trombosis)", "Fístulas arteriovenosas (si hemodiálisis)"],
        "pathology_signs": ["Trombosis venosa profunda (vena incompresible, trombo intraluminal)", "Estenosis carotídea (placa con reducción >50% del lumen)", "Aneurisma de aorta abdominal (diámetro >3cm)", "Insuficiencia venosa (reflujo >0.5 segundos)", "Oclusión arterial aguda (ausencia de flujo distal)"],
        "measurements": ["Espesor íntima-media carotídeo (normal: <0.9mm)", "Velocidad pico sistólica en carótida interna", "Diámetro aórtico máximo", "Índice tobillo-brazo"],
        "red_flags": ["TVP proximal (iliofemoral) con riesgo de TEP", "Estenosis carotídea >70% sintomática", "Aneurisma aórtico >5.5cm o en expansión rápida", "Isquemia aguda de miembro"]
    },

    "obstetricia": {
        "display_name": "Obstetricia (Control Prenatal)",
        "focus_areas": ["Biometría fetal (DBP, CC, CA, LF)", "Anatomía fetal (SNC, corazón, abdomen, columna)", "Placenta (ubicación, grado, inserción del cordón)", "Líquido amniótico (ILA o bolsillo mayor)", "Cuello uterino (longitud cervical)"],
        "pathology_signs": ["Restricción del crecimiento intrauterino (biometría <percentil 10)", "Polihidramnios (ILA >25cm) u oligoamnios (ILA <5cm)", "Placenta previa (inserción sobre OCI)", "Malformaciones fetales (defectos del tubo neural, cardiopatías, onfalocele)", "Desprendimiento prematuro de placenta (hematoma retroplacentario)", "Circular de cordón"],
        "measurements": ["Edad gestacional por biometría fetal", "Peso fetal estimado", "Longitud cervical (riesgo si <25mm)", "Índice de líquido amniótico"],
        "red_flags": ["Desprendimiento de placenta con sangrado activo", "Vasa previa", "Bradicardia fetal sostenida", "Oligoamnios severo (ILA <2cm)"],
        "organ_measurements_schema": {
            "feto": {
                "dbp_mm": None,
                "cc_mm": None,
                "ca_mm": None,
                "lf_mm": None,
                "peso_estimado_g": None,
                "edad_gestacional_semanas": None,
                "fc_lpm": None
            },
            "placenta": {
                "grado_maduracion": None,
                "espesor_mm": None
            },
            "liquido_amniotico": {
                "ila_mm": None,
                "bolsillo_mayor_mm": None
            },
            "cuello_uterino": {
                "longitud_mm": None
            }
        }
    },

    "nefrologia": {
        "display_name": "Nefrología",
        "focus_areas": ["Riñones (tamaño, corteza, ecogenicidad cortical)", "Diferenciación corticomedular", "Sistema pielocalicial", "Flujo renal (Doppler, índice de resistencia)", "Vejiga y volumen residual"],
        "pathology_signs": ["Nefropatía crónica (riñones pequeños <9cm, corteza adelgazada, hiperecogénica)", "Nefritis intersticial (riñones aumentados, edematosos)", "Trombosis de vena renal (riñón aumentado, ausencia de flujo venoso)", "Quistes renales (clasificación Bosniak)", "Necrosis papilar"],
        "measurements": ["Longitud renal bilateral", "Espesor cortical (normal: >10mm)", "Índice de resistencia arterial (normal: 0.55-0.70)", "Clasificación Bosniak de quistes"],
        "red_flags": ["Trombosis bilateral de venas renales", "Uropatía obstructiva bilateral", "Riñón único con obstrucción"]
    },

    "oncologia": {
        "display_name": "Oncología / Imágenes Oncológicas",
        "focus_areas": ["Lesión primaria (tamaño, bordes, vascularización)", "Ganglios linfáticos regionales y a distancia", "Metástasis hepáticas, pulmonares, óseas", "Respuesta al tratamiento (criterios RECIST)"],
        "pathology_signs": ["Masa sólida con bordes irregulares y neovascularización", "Adenopatía patológica (redondeada, >1cm eje corto, sin hilio graso)", "Lesiones hepáticas en 'diana' (metástasis)", "Lesiones óseas líticas u osteoblásticas múltiples", "Derrame pleural maligno (nodularidad pleural)", "Carcinomatosis peritoneal (implantes en peritoneo, ascitis)"],
        "measurements": ["Diámetro mayor de lesión target (RECIST 1.1)", "Suma de diámetros de lesiones target", "Eje corto de ganglios patológicos"],
        "red_flags": ["Compresión medular por metástasis vertebral", "Metástasis cerebral con efecto de masa", "Trombosis tumoral de vena cava", "Síndrome de vena cava superior"]
    },

    "medicina_interna": {
        "display_name": "Medicina Interna / Clínica Médica",
        "focus_areas": ["Evaluación multiorgánica sistemática", "Tórax (corazón y pulmones)", "Abdomen completo", "Grandes vasos", "Búsqueda de colecciones o líquido libre"],
        "pathology_signs": ["Hepatoesplenomegalia", "Derrames (pleural, pericárdico, ascitis)", "Signos de insuficiencia cardíaca (redistribución vascular, cardiomegalia)", "Trombosis venosa profunda", "Adenopatías generalizadas (descartar linfoma)", "Signos de hipertensión portal"],
        "measurements": ["Diámetro esplénico (normal: <13cm)", "Diámetro hepático", "Índice cardiotorácico", "Calibre de vena porta (normal: <13mm)"],
        "red_flags": ["Derrame pericárdico masivo", "Ascitis a tensión con compromiso respiratorio", "Tromboembolismo pulmonar", "Adenopatías con sospecha de linfoma"],
        "organ_measurements_schema": {
            "higado": {
                "diametro_longitudinal_mm": None
            },
            "bazo": {
                "diametro_longitudinal_mm": None
            },
            "vena_porta": {
                "calibre_mm": None
            },
            "aorta_abdominal": {
                "diametro_mm": None
            },
            "corazon": {
                "indice_cardiotoracio": None
            }
        }
    },

    "general": {
        "display_name": "Radiología General",
        "focus_areas": [
            "Todas las estructuras anatómicas visibles en el plano del estudio",
            "Simetría y proporciones generales",
            "Tejidos blandos y espacios anatómicos"
        ],
        "pathology_signs": [
            "Cualquier masa, colección líquida o alteración de la densidad",
            "Signos inflamatorios (edema, engrosamiento de paredes)",
            "Calcificaciones atípicas",
            "Líquido libre en cavidades"
        ],
        "measurements": [
            "Dimensiones de cualquier hallazgo anormal en sus 3 ejes"
        ],
        "red_flags": [
            "Masa de características malignas (bordes irregulares, vascularización anómala)",
            "Colecciones líquidas con gas (absceso)",
            "Cualquier hallazgo que sugiera proceso agudo"
        ],
        "organ_measurements_schema": {
            "hallazgo_principal": {
                "dim1_mm": None,
                "dim2_mm": None,
                "dim3_mm": None
            }
        }
    }
}


def get_merged_prompts() -> dict:
    prompts = SPECIALTY_PROMPTS.copy()
    custom_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "custom_prompts.json")
    if os.path.exists(custom_file):
        try:
            with open(custom_file, "r", encoding="utf-8") as f:
                custom = json.load(f)
                for k, v in custom.items():
                    if k in prompts:
                        prompts[k].update(v)
                    else:
                        prompts[k] = v
        except Exception as e:
            print(f"Error loading custom prompts: {e}")
    return prompts

def get_specialty_names() -> dict:
    """Retorna un dict {clave: nombre_display} de todas las especialidades disponibles."""
    prompts = get_merged_prompts()
    return {k: v.get("display_name", k.capitalize()) for k, v in prompts.items()}

def _build_organ_analysis_template(schema: dict) -> str:
    examples = []
    for organ, fields in schema.items():
        examples.append({
            "organ": organ,
            "status": "normal | alterado | no evaluable",
            "signs": ["hallazgo si existe, omitir si no hay"],
            "measurements": fields
        })
    return json.dumps(examples, ensure_ascii=False, indent=4)


def build_specialty_prompt(
    specialty: str = "general",
    clinical_context: str = None,
    patient_age: str = None,
    patient_sex: str = None,
    dicom_metadata: dict = None
) -> str:
    """
    Construye un prompt de visión médica optimizado según la especialidad
    y los parámetros clínicos recibidos.
    """
    prompts = get_merged_prompts()
    
    # Normalizar especialidad (por clave exacta, minúsculas, o display_name)
    resolved_spec = None
    spec_clean = specialty.lower().strip()
    
    if spec_clean in prompts:
        resolved_spec = prompts[spec_clean]
    else:
        # Buscar por display_name o clave aproximada
        for k, v in prompts.items():
            if k.lower() == spec_clean or v.get("display_name", "").lower().strip() == spec_clean:
                resolved_spec = v
                break
                
    if not resolved_spec:
        resolved_spec = prompts.get("general", SPECIALTY_PROMPTS["general"])
        
    spec = resolved_spec

    # Contexto del paciente
    patient_info = ""
    if patient_age:
        patient_info += f"\n- Edad del paciente: {patient_age}"
    if patient_sex:
        patient_info += f"\n- Sexo: {patient_sex}"
    if clinical_context:
        patient_info += f"\n- Contexto clínico: {clinical_context}"
    if dicom_metadata:
        patient_info += f"\n- Metadatos técnicos del equipo: {dicom_metadata}"

    focus = "\n".join(f"   - {f}" for f in spec["focus_areas"])
    signs = "\n".join(f"   - {s}" for s in spec["pathology_signs"])
    measurements = "\n".join(f"   - {m}" for m in spec["measurements"])
    red_flags = "\n".join(f"   - ⚠️ {r}" for r in spec["red_flags"])

    schema = spec.get("organ_measurements_schema")
    if schema:
        organ_analysis_example = _build_organ_analysis_template(schema)
        measurements_note = (
            "IMPORTANTE: En el campo 'measurements' de cada órgano usa EXACTAMENTE "
            "los campos numéricos del esquema. Completa con el valor medido (float) "
            "o null si la estructura no es visible en la imagen. NO uses texto libre."
        )
    else:
        organ_analysis_example = json.dumps([{
            "organ": "nombre del órgano/estructura",
            "status": "normal | alterado | no evaluable",
            "signs": ["hallazgo 1", "hallazgo 2"],
            "measurements": "mediciones si aplica"
        }], ensure_ascii=False, indent=4)
        measurements_note = ""

    prompt = f"""
Sos un sistema de análisis de diagnóstico por imágenes con dos roles diferenciados.
Debés generar AMBAS secciones del informe.
{patient_info}

═══════════════════════════════════════
ROL 1 — DESCRIPCIÓN TÉCNICA (como técnico en imágenes)
═══════════════════════════════════════
Describí objetivamente lo que aparece en la imagen, sin interpretación clínica:
- Modalidad de estudio y región anatómica
- Calidad de imagen (buena / regular / limitada por artefactos)
- Estructuras anatómicas visibles
- Parámetros técnicos inferibles (profundidad, frecuencia aproximada, plano de corte)
- Artefactos presentes si los hay (sombra acústica, reverberación, ruido)
SIN hacer diagnóstico. Solo describir lo que se ve.

═══════════════════════════════════════
ROL 2 — ANÁLISIS MÉDICO (como especialista en {spec['display_name']})
═══════════════════════════════════════

PROTOCOLO DE ANÁLISIS — {spec['display_name'].upper()}

1. ÁREAS DE FOCO:
{focus}

2. SIGNOS PATOLÓGICOS A BUSCAR:
{signs}

3. MEDICIONES CLÍNICAS:
{measurements}

4. BANDERAS ROJAS:
{red_flags}

INSTRUCCIONES:
- Correlaciona con el contexto clínico del paciente si fue proporcionado.
- Distingue artefactos de patología real.
- NO inventes hallazgos. Si no hay patología: "Sin hallazgos patológicos significativos".
{measurements_note}

═══════════════════════════════════════
FORMATO DE RESPUESTA (JSON estricto)
═══════════════════════════════════════
{{
    "technical_description": "descripción técnica objetiva en 2-4 oraciones, en español, como la escribiría un técnico en imágenes",
    "specialty": "{specialty}",
    "area_anatomica": "región evaluada",
    "finding": "hallazgo principal en una frase",
    "pathology_status": "red | yellow | green",
    "report": "informe médico detallado con hallazgos e impresión diagnóstica, 3-6 oraciones",
    "clinical_correlation": "correlación con el contexto clínico si fue proporcionado",
    "organ_analysis": {organ_analysis_example},
    "critical_findings": ["hallazgos que requieren acción inmediata"],
    "recommendations": ["estudios complementarios si corresponde"],
    "confidence": 0.0
}}

pathology_status: "red" = hallazgo crítico / urgente. "yellow" = hallazgo moderado / requiere seguimiento. "green" = normal o sin hallazgos significativos.
"""
    return prompt.strip()
