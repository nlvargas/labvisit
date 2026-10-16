"""Demo catalog. Prices follow Clínica Adventista's public 2026 price list (Fonasa and private
columns); lines marked "est." weren't on that list and are estimates. Labs replace all of this."""

URINE_MORNING = "Recolectar la primera orina de la mañana, segundo chorro, en frasco estéril, después de un aseo genital con agua."
URINE_24H = "Recolectar toda la orina de 24 horas en el bidón que entrega el laboratorio, partiendo después de la primera orina del día."
STOOL = "Recolectar una muestra de deposiciones en el frasco que entrega el laboratorio."
STOOL_SERIAL = "Recolectar tres muestras de deposiciones en días distintos, en el frasco con líquido que entrega el laboratorio."
GRAHAM = "Tomar la muestra en la mañana, antes de bañarse y de ir al baño."
BEFORE_10 = "La muestra debe tomarse antes de las 10:00 de la mañana."
PROLACTIN = "La muestra debe tomarse antes de las 10:00, después de 20 minutos de reposo."
PSA = "Evitar actividad sexual y andar en bicicleta las 48 horas previas."
GLUCOSE_CURVE = "El examen dura alrededor de 2 horas, en reposo. No fumar ni hacer ejercicio antes ni durante el examen."
NO_EXERCISE = "No hacer ejercicio intenso las 24 horas previas."
GYNECOLOGIC = "No tener relaciones sexuales ni usar óvulos o duchas vaginales las 48 horas previas. No se toma durante la menstruación."

# (name, synonyms, sample_type, fasting_hours, prep_text, fonasa_clp, private_clp)
EXAMS = [
    # Hematology and coagulation
    ("Hemograma", ["hemograma completo", "hmg", "hemograma con vhs"], "blood", 0, "", 5070, 7605),
    ("Velocidad de sedimentación", ["vhs", "vsg", "eritrosedimentacion"], "blood", 0, "", 910, 1365),
    ("Recuento de plaquetas", ["plaquetas", "recuento plaquetario"], "blood", 0, "", 2130, 3195),
    ("Recuento de reticulocitos", ["reticulocitos"], "blood", 0, "", 1650, 2475),
    ("Grupo sanguíneo y Rh", ["grupo y rh", "grupo sanguineo", "grupo rh", "clasificacion sanguinea"], "blood", 0, "", 4100, 6150),
    ("Tiempo de protrombina", ["tp", "inr", "tp inr", "protrombina"], "blood", 0, "", 2540, 3810),
    ("TTPK", ["ttpa", "tiempo de tromboplastina parcial", "ttp"], "blood", 0, "", 3920, 5880),
    ("Fibrinógeno", ["fibrinogeno"], "blood", 0, "", 4190, 6285),
    ("Coombs directo", ["test de coombs directo", "coombs"], "blood", 0, "", 2290, 3435),
    # Glucose metabolism
    ("Glicemia", ["glucosa", "glucemia", "glicemia en ayunas", "glicemia basal"], "blood", 8, "", 2050, 3075),
    ("Prueba de tolerancia a la glucosa", ["ptgo", "ttgo", "curva de glicemia", "curva de tolerancia a la glucosa",
                                          "test de tolerancia a la glucosa", "glicemia post carga", "glicemia postcarga"],
     "blood", 8, GLUCOSE_CURVE, 9540, 14310),
    ("Hemoglobina glicosilada", ["hba1c", "hb a1c", "hemoglobina glicada", "hb glicosilada"], "blood", 0, "", 7420, 11130),
    ("Insulina basal", ["insulina", "insulinemia basal", "insulinemia"], "blood", 8, "", 8400, 12600),
    ("Curva de insulina", ["insulina post carga", "curva insulinica"], "blood", 8, GLUCOSE_CURVE, 22660, 33990),
    # Chemistry
    ("Perfil bioquímico", ["pbq", "perfil bioquimico", "bioquimico"], "blood", 12, "", 14340, 21510),
    ("Perfil lipídico", ["perfil de lipidos", "lipidos", "perfil lipidico"], "blood", 12, "", 10210, 15315),
    ("Colesterol total", ["colesterol", "colesterolemia"], "blood", 12, "", 2220, 3330),
    ("Colesterol HDL", ["hdl", "hdl colesterol"], "blood", 12, "", 3310, 4965),
    ("Colesterol LDL", ["ldl", "ldl colesterol"], "blood", 12, "", 3310, 4965),  # est.
    ("Triglicéridos", ["trigliceridos", "tg", "trigliceridemia"], "blood", 12, "", 2900, 4350),
    ("Creatinina", ["crea", "creatininemia", "creatinina plasmatica"], "blood", 0, "", 2190, 3285),
    ("Nitrógeno ureico", ["bun", "nitrogeno ureico", "nu", "uremia"], "blood", 0, "", 2160, 3240),
    ("Ácido úrico", ["acido urico", "ac urico", "uricemia"], "blood", 8, "", 2500, 3750),
    ("Electrolitos plasmáticos", ["elp", "electrolitos", "ely", "sodio potasio cloro", "na k cl"], "blood", 0, "", 6330, 9495),
    ("Calcio", ["calcemia", "calcio total"], "blood", 0, "", 2270, 3405),
    ("Calcio iónico", ["calcio ionico", "calcio ionizado"], "blood", 0, "", 4500, 6750),  # est.
    ("Fósforo", ["fosforo", "fosfemia"], "blood", 0, "", 3010, 4515),
    ("Magnesio", ["magnesemia"], "blood", 0, "", 5230, 7845),
    ("Perfil hepático", ["pruebas hepaticas", "perfil hepatico", "pruebas de funcion hepatica"], "blood", 8, "", 16780, 25170),
    ("Bilirrubina total y directa", ["bilirrubina", "bilirrubinemia", "bilirrubina total"], "blood", 8, "", 2400, 3600),
    ("Transaminasa GOT", ["got", "ast", "transaminasa oxaloacetica"], "blood", 0, "", 3040, 4560),
    ("Transaminasa GPT", ["gpt", "alt", "transaminasa piruvica"], "blood", 0, "", 3040, 4560),
    ("GGT", ["gamma glutamil transferasa", "gamma gt", "ggtp"], "blood", 0, "", 3680, 5520),
    ("Fosfatasa alcalina", ["fosfatasas alcalinas"], "blood", 0, "", 2100, 3150),
    ("Proteínas totales y albúmina", ["proteinas totales", "albumina", "proteinemia"], "blood", 0, "", 4840, 7260),
    ("Amilasa", ["amilasemia"], "blood", 0, "", 3920, 5880),
    ("Lipasa", ["lipasemia"], "blood", 0, "", 4350, 6525),
    ("CK total", ["ck", "cpk", "creatinquinasa"], "blood", 0, NO_EXERCISE, 6240, 9360),
    ("LDH", ["lactato deshidrogenasa", "deshidrogenasa lactica"], "blood", 0, "", 3920, 5880),
    ("Proteína C reactiva", ["pcr", "proteina c reactiva", "pcr cuantitativa"], "blood", 0, "", 9980, 14970),
    # Iron and vitamins
    ("Ferritina", ["ferritinemia", "ferritina serica"], "blood", 0, "", 9870, 14805),
    ("Perfil de hierro", ["perfil de fierro", "fierro serico", "hierro serico", "tibc", "saturacion de transferrina"],
     "blood", 8, BEFORE_10, 7580, 11370),
    ("Vitamina D", ["25 oh vitamina d", "vit d", "25 hidroxivitamina d", "vitamina d total"], "blood", 0, "", 27650, 41475),
    ("Vitamina B12", ["vit b12", "b12", "cianocobalamina", "cobalamina"], "blood", 0, "", 12450, 18675),
    ("Ácido fólico", ["acido folico", "folato", "folatos"], "blood", 0, "", 8220, 12330),
    # Thyroid and hormones
    ("TSH", ["tirotropina", "hormona estimulante de tiroides", "tsh ultrasensible"], "blood", 0, "", 7420, 11130),
    ("T4 libre", ["t4l", "tiroxina libre", "t4 l"], "blood", 0, "", 8540, 12810),
    ("T4 total", ["t4", "tiroxina", "tiroxinemia"], "blood", 0, "", 7420, 11130),
    ("T3", ["t3 total", "triyodotironina"], "blood", 0, "", 7710, 11565),
    ("T3 libre", ["t3l", "triyodotironina libre"], "blood", 0, "", 21690, 32535),
    ("Anticuerpos antitiroperoxidasa", ["anti tpo", "atpo", "anticuerpos anti tpo", "antimicrosomales"], "blood", 0, "",
     13000, 19500),  # est.
    ("Anticuerpos antitiroglobulina", ["anti tg", "antitiroglobulina", "atg"], "blood", 0, "", 13000, 19500),  # est.
    ("Cortisol", ["cortisol am", "cortisol plasmatico", "cortisolemia"], "blood", 0, BEFORE_10, 9170, 13755),
    ("Prolactina", ["prl"], "blood", 0, PROLACTIN, 9020, 13530),
    ("FSH", ["hormona foliculo estimulante"], "blood", 0, "", 9020, 13530),
    ("LH", ["hormona luteinizante"], "blood", 0, "", 9040, 13560),
    ("Estradiol", ["e2"], "blood", 0, "", 8860, 13290),
    ("Progesterona", ["progesteronemia"], "blood", 0, "", 8540, 12810),
    ("Testosterona total", ["testosterona"], "blood", 0, BEFORE_10, 9380, 14070),
    ("DHEA-S", ["dheas", "dhea s", "sulfato de dehidroepiandrosterona"], "blood", 0, "", 11440, 17160),
    ("Subunidad beta HCG", ["beta hcg", "bhcg", "b hcg", "hcg cuantitativa", "test de embarazo en sangre"], "blood", 0, "",
     8830, 13245),
    ("Hormona paratiroidea", ["pth", "paratohormona", "pth intacta"], "blood", 0, "", 13760, 20640),
    # Tumor markers
    ("Antígeno prostático específico", ["psa", "antigeno prostatico", "psa total"], "blood", 0, PSA, 14940, 22410),
    ("PSA total y libre", ["psa libre", "antigeno prostatico libre"], "blood", 0, PSA, 24690, 37035),
    ("Antígeno carcinoembrionario", ["cea", "ace", "antigeno carcinoembrionario"], "blood", 0, "", 11620, 17430),
    ("CA 125", ["ca125", "ca 12 5"], "blood", 0, "", 15490, 23235),
    ("CA 19-9", ["ca19 9", "ca 199"], "blood", 0, "", 15490, 23235),
    # Serology and immunology
    ("VIH", ["test de vih", "elisa vih", "hiv", "virus de inmunodeficiencia humana"], "blood", 0, "", 8880, 13320),
    ("VDRL", ["rpr", "sifilis"], "blood", 0, "", 5090, 7635),
    ("Antígeno de superficie hepatitis B", ["hbsag", "hepatitis b", "ag superficie hepatitis b"], "blood", 0, "", 8990, 13485),
    ("Anticuerpos hepatitis C", ["anti hcv", "hcv", "hepatitis c", "virus hepatitis c"], "blood", 0, "", 13730, 20595),
    ("Factor reumatoideo", ["factor reumatoide", "fr", "latex ar"], "blood", 0, "", 4400, 6600),
    ("Anticuerpos antinucleares", ["ana", "anticuerpos anti nucleares", "aan"], "blood", 0, "", 12450, 18675),
    ("Antiestreptolisina O", ["aso", "asto", "antiestreptolisina"], "blood", 0, "", 7680, 11520),
    ("Anticuerpos antitransglutaminasa IgA", ["antitransglutaminasa", "ttg iga", "anti ttg"], "blood", 0, "", 19920, 29880),
    ("Toxoplasmosis IgG", ["toxoplasma igg", "toxoplasmosis"], "blood", 0, "", 10000, 15000),  # est.
    # Urine
    ("Orina completa", ["oc", "examen de orina", "orina", "sedimento de orina"], "urine", 0, URINE_MORNING, 3140, 4710),
    ("Urocultivo", ["uc", "cultivo de orina", "urocultivo con antibiograma"], "urine", 0, URINE_MORNING, 6080, 9120),
    ("Microalbuminuria", ["albuminuria", "relacion albumina creatinina", "rac"], "urine", 0, URINE_MORNING, 4660, 6990),
    ("Clearance de creatinina", ["depuracion de creatinina", "clearance creatinina"], "urine", 0, URINE_24H, 4830, 7245),
    ("Proteinuria de 24 horas", ["proteinuria 24 horas", "proteinuria", "proteinas en orina de 24 horas"], "urine", 0,
     URINE_24H, 2930, 4395),
    # Stool
    ("Parasitológico seriado de deposiciones", ["psd", "parasitologico seriado", "parasitologico", "coproparasitologico"],
     "stool", 0, STOOL_SERIAL, 4880, 7320),
    ("Coprocultivo", ["cultivo de deposiciones"], "stool", 0, STOOL, 6820, 10230),
    ("Hemorragias ocultas en deposiciones", ["sangre oculta en deposiciones", "hemorragia oculta", "test de sangre oculta"],
     "stool", 0, STOOL_SERIAL, 1940, 2910),
    ("Leucocitos fecales", ["leucocitos en deposiciones"], "stool", 0, STOOL, 1940, 2910),
    ("Antígeno Helicobacter pylori en deposiciones", ["helicobacter pylori", "h pylori", "antigeno h pylori"], "stool", 0,
     STOOL, 15000, 22500),  # est.
    ("Test de Graham", ["graham", "test de graham para oxiuros"], "other", 0, GRAHAM, 3460, 5190),
    # Molecular
    ("PCR virus papiloma humano", ["vph", "pcr vph", "hpv", "virus papiloma humano", "genotipificacion vph"], "other", 0,
     GYNECOLOGIC, 40000, 60000),  # est.
    ("PCR Chlamydia y gonorrea", ["chlamydia", "clamidia", "pcr chlamydia", "gonorrea", "neisseria gonorrhoeae"], "other", 0,
     GYNECOLOGIC, 43470, 65205),
]

# (name, kind, which price column)
COVERAGES = [("Fonasa", "fonasa", "fonasa"), ("Isapre", "isapre", "private")]


# Av. Salvador 135, Providencia (geocoded with OpenStreetMap). Visit fee = base + per km, placeholders.
LAB_LOCATION = (-33.43519, -70.62627)
LAB_STYLE = {
    "brand_color": "#5dc1cf", "font": "montserrat", "corners": "square", "phone": "(56-2) 2274 3504",
    "tagline": "Laboratorio Diagnóstika Ltda.", "address_line": "Av. Salvador 135, Providencia",
    "website_url": "https://www.biodata.cl/laboratorio/",
}
VISIT_FEE = {"visit_base_fee_clp": 18000, "visit_fee_per_km_clp": 500, "max_visit_km": 25}

# placeholder office hours (weekday 0 = Monday); confirm with the lab
OPENING_HOURS = [(day, "08:00", "17:00") for day in range(5)] + [(5, "08:00", "12:00")]
