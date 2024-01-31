# Leer el archivo
with open('bandas.txt', 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

# Eliminar duplicados convirtiendo las líneas en un conjunto
lines = list(set(lines))

# Escribir las líneas de nuevo en el archivo
with open('bandas_corregidos.txt', 'w', encoding='utf-8') as f:
    for line in lines:
        f.write(line + '\n')