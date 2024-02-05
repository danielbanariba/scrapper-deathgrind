import os
import cv2
import shutil
import numpy as np
from moviepy.editor import ImageClip, concatenate_audioclips, AudioFileClip
from PIL import Image, ImageFilter

main_dir_path = 'D:\\script_video\\'

# Recorre todos los directorios en la ruta principal
for dirname in os.listdir(main_dir_path):
    dir_path = os.path.join(main_dir_path, dirname)
    
    if os.path.isdir(dir_path):
        new_dir_path = dir_path.replace('–', '-')
        
        # Mueve el directorio si el nombre ha cambiado
        if dir_path != new_dir_path:
            shutil.move(dir_path, new_dir_path)

# Directorio donde se guardará el video renderizado
output_dir = r'D:\videos_renderizados'

# Crea el directorio de salida si no existe
os.makedirs(output_dir, exist_ok=True)

# Obtiene la lista de archivos en la carpeta
files = os.listdir(dir_path)

# Filtra la lista para incluir solo los archivos .mp3
songs = [os.path.join(dir_path, file) for file in files if file.endswith('.mp3')]

# Si no hay canciones en la carpeta, termina el script
if not songs:
    print("No se encontraron canciones en la carpeta.")
    exit()

# Busca la imagen en la carpeta
image_file = next((file for file in files if file.endswith('.jpg')), None)

# Si no hay imagen en la carpeta, termina el script
if image_file is None:
    print("No se encontró una imagen en la carpeta.")
    exit()

# Crea clips de audio a partir de tus canciones
audio_clips = [AudioFileClip(song) for song in songs]

# Concatena los clips de audio
concatenated_audio = concatenate_audioclips(audio_clips)

# Abre la imagen original
img = Image.open(os.path.join(dir_path, image_file))

# Calcula el factor de escala para llenar el ancho
scale_factor = max(3840 / img.width, 2160 / img.height)

# Calcula las nuevas dimensiones de la imagen
new_width = round(img.width * scale_factor)
new_height = round(img.height * scale_factor)

# Redimensiona la imagen
img = img.resize((new_width, new_height))

# Si la imagen es más alta que la altura deseada, recorta la parte superior e inferior
if new_height > 2160:
    top = (new_height - 2160) // 2
    img = img.crop((0, top, new_width, top + 2160))

# Aplica el efecto borroso
background = img.filter(ImageFilter.GaussianBlur(radius=20))  # Puedes ajustar el radio para cambiar la cantidad de desenfoque

# Guarda la imagen de fondo
background.save('background.jpg')

# Crea un clip de video a partir de tu imagen final
video = ImageClip('background.jpg', duration=concatenated_audio.duration)

# Añade el audio al video
video = video.set_audio(concatenated_audio)

# Establece los frames por segundo del video
video.fps = 24

# Obtiene el nombre de la carpeta
folder_name = os.path.basename(dir_path)

# Escribe el video final en el directorio de salida con el nombre de la carpeta
video.write_videofile(os.path.join(output_dir, f'{folder_name}.mp4'), codec='h264_nvenc')