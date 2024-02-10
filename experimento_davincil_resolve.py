import sys
sys.path.append('C:\\ProgramData\\Blackmagic Design\\DaVinci Resolve\\Support\\Developer\\Scripting\\Modules\DaVinciResolveScript.py')

try:
    import DaVinciResolveScript as dvr_script
except ModuleNotFoundError:
    print("No se pudo importar el módulo DaVinciResolveScript. Verifica la ruta proporcionada.")
    sys.exit(1)

resolve = dvr_script.scriptapp("Resolve")
projectManager = resolve.GetProjectManager()

try:
    projectManager.CreateProject("Hello World")
except Exception as e:
    print(f"No se pudo crear el proyecto: {e}")