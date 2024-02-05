import os
from moviepy.editor import ImageClip, concatenate_audioclips, AudioFileClip

# Directorio donde están tus canciones e imagen
dir_path = r'D:\script_video\Desoectomy–Maul-Desecrated-Atrocity'

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

# Crea un clip de video a partir de tu imagen
video = ImageClip(os.path.join(dir_path, image_file), duration=concatenated_audio.duration)

# Añade el audio al video
video = video.set_audio(concatenated_audio)

# Establece los frames por segundo del video
video.fps = 24

# Obtiene el nombre de la carpeta
folder_name = os.path.basename(dir_path)

# Escribe el video final en el directorio de salida con el nombre de la carpeta
video.write_videofile(os.path.join(output_dir, f'{folder_name}.mp4'), codec='h264_nvenc')