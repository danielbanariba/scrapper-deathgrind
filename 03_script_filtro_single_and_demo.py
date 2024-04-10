# Palabras clave
keywords = ["[Demo]", "[Single]", "[Split]", "[Compilation]"]

# Listas para almacenar las bandas
bandas_con_keywords = []
bandas_sin_keywords = []

# Leer el archivo de bandas aprobadas
# Yo creo manualmente el alrchivo bandas_corregidos.txt
with open('bandas_corregidos.txt', 'r', encoding='utf-8') as f:
    bandas = f.read().splitlines()

# Clasificar las bandas
for banda in bandas:
    if any(keyword in banda for keyword in keywords):
        bandas_con_keywords.append(banda)
    else:
        bandas_sin_keywords.append(banda)

# Guardar las bandas en archivos
with open('demo-single-split-compilation.txt', 'w', encoding='utf-8') as f:
    for banda in bandas_con_keywords:
        f.write(banda + '\n')

with open('album-ep.txt', 'w', encoding='utf-8') as f:
    for banda in bandas_sin_keywords:
        f.write(banda + '\n')