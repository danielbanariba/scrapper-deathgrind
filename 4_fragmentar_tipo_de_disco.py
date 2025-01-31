import os

# Palabras clave normalizadas
keywords = [
    "[Album]",
    "[EP]",
    "[Demo]",
    "[Split]",
    "[Compilation]",
    "[Single]",
    "[Maxi-Single]",
    "[Live]",
    "[Promo]",
    "[Discography]"
]

# Leer el archivo de bandas
with open('bandas.txt', 'r', encoding='utf-8') as f:
    bandas = f.read().splitlines()

# Diccionario para almacenar las bandas por tipo
bandas_por_tipo = {keyword: [] for keyword in keywords}
bandas_sin_clasificar = []  # Para bandas que no coinciden con ninguna categoría

# Clasificar las bandas
for banda in bandas:
    matched = False
    for keyword in keywords:
        if keyword in banda:
            bandas_por_tipo[keyword].append(banda)
            matched = True
            break  # Importante: romper después de la primera coincidencia
    if not matched:
        bandas_sin_clasificar.append(banda)

# Guardar las bandas en archivos separados
for tipo, bandas in bandas_por_tipo.items():
    if bandas:  # Solo crear archivo si hay bandas de ese tipo
        filename = tipo.strip('[]') + '.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            for banda in bandas:
                f.write(banda + '\n')

# Guardar bandas sin clasificar
if bandas_sin_clasificar:
    with open('Sin_Clasificar.txt', 'w', encoding='utf-8') as f:
        for banda in bandas_sin_clasificar:
            f.write(banda + '\n')

# Eliminar el archivo original
os.remove('bandas.txt')