# Optimizador de rutas de carguío y transporte minero

Prototipo académico en Python con mapa interactivo (Streamlit + Folium), red de caminos,
optimización multicriterio de rutas, retorno vacío, asignación heurística de camiones y
estimaciones de tiempo de ciclo, combustible, costo y producción teórica.

## Requisitos
- Python 3.10 o superior recomendado.
- Conexión a Internet al instalar las bibliotecas.
- Los datos del ejemplo son ficticios y solo sirven para demostración.

## Instalación
En una terminal, dentro de la carpeta del proyecto:

```bash
python -m venv .venv
```

Activar el entorno:
- Windows: `.venv\\Scripts\\activate`
- macOS/Linux: `source .venv/bin/activate`

Instalar dependencias:

```bash
pip install -r requirements.txt
```

## Ejecutar

```bash
streamlit run app.py
```

Se abrirá la aplicación en el navegador. En el panel izquierdo puedes ajustar:
- cantidad y capacidad de camiones;
- tiempos de carguío y descarga;
- precio de combustible;
- caminos cerrados;
- importancia relativa de tiempo, combustible y distancia.

En el mapa:
- azul: viaje cargado;
- naranjo discontinuo: retorno vacío;
- gris: red de caminos disponible;
- verde: pala; rojo: destino de descarga; azul: cruce.

## Modelo de optimización
Dijkstra encuentra rutas con un costo combinado. Las prioridades de tiempo, combustible y
distancia se normalizan para sumar 100 %. Después se calcula el ciclo completo cargado +
carguío + descarga + retorno vacío. Una heurística asigna camiones considerando una
penalización simple por concentración en una misma pala.

## Limitaciones
Este no es un sistema de despacho listo para operación minera. No usa GPS, telemetría,
pendientes reales, tráfico en tiempo real ni restricciones de seguridad certificadas.
La asignación de flota es heurística y no garantiza el óptimo global. Valida y calibra todos
los parámetros con datos reales antes de usarlo en terreno.
