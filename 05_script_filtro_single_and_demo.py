# Palabras clave
keywords = ["[Demo]", "[Single]", "[Split]", "[Compilation]"]

# Listas para almacenar las bandas
bandas_con_keywords = []
bandas_sin_keywords = []

# Leer el archivo de bandas aprobadas
with open('total_bandas_aprobadas.txt', 'r') as f:
    bandas = f.read().splitlines()

# Clasificar las bandas
for banda in bandas:
    if any(keyword in banda for keyword in keywords):
        bandas_con_keywords.append(banda)
    else:
        bandas_sin_keywords.append(banda)

# Guardar las bandas en archivos
with open('bandas_con_keywords.txt', 'w') as f:
    for banda in bandas_con_keywords:
        f.write(banda + '\n')

with open('bandas_sin_keywords.txt', 'w') as f:
    for banda in bandas_sin_keywords:
        f.write(banda + '\n')