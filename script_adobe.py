from pymiere import wrappers

# Abrir un proyecto en Premiere
project = wrappers.Project.open_project(r"C:\ruta\al\proyecto.prproj")

# Obtener la primera secuencia en el proyecto
sequence = project.sequences[0]

# Agregar un clip a la secuencia
clip = wrappers.Clip(r"C:\ruta\al\clip.mp4")
sequence.insertClip(clip, 0)