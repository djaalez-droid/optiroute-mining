import math
from collections import defaultdict

import folium
import networkx as nx
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium


# ============================================================
# OPTIMIZADOR DE CARGUIO Y TRANSPORTE MINERO - DEMOSTRACION
# Datos ficticios para una mina a cielo abierto.
# ============================================================

st.set_page_config(
    page_title="Optimizador de rutas mineras",
    page_icon="🚚",
    layout="wide",
)

st.title("⛏️ Sistema de optimización de carguío y transporte")
st.caption(
    "Prototipo académico con mapa interactivo, rutas alternativas, "
    "asignación de camiones y evaluación conjunta de tiempo, combustible y producción."
)

# Coordenadas ficticias alrededor de una mina hipotética en Chile.
# Las coordenadas solo sirven para representar el trazado en el mapa.
NODES = {
    "Pala Norte": {"lat": -22.9500, "lon": -68.1800, "kind": "pala"},
    "Pala Sur": {"lat": -22.9560, "lon": -68.1690, "kind": "pala"},
    "Cruce A": {"lat": -22.9460, "lon": -68.1710, "kind": "cruce"},
    "Cruce B": {"lat": -22.9610, "lon": -68.1780, "kind": "cruce"},
    "Cruce C": {"lat": -22.9490, "lon": -68.1590, "kind": "cruce"},
    "Cruce D": {"lat": -22.9660, "lon": -68.1630, "kind": "cruce"},
    "Botadero 1": {"lat": -22.9400, "lon": -68.1530, "kind": "botadero"},
    "Chancador": {"lat": -22.9720, "lon": -68.1510, "kind": "botadero"},
}

# Cada conexión es una vía bidireccional. Distancia y velocidad son
# estimaciones de ejemplo; no representan una operación real.
ROAD_DATA = [
    ("Pala Norte", "Cruce A", 1.8, 25, 32, 2.7, 1.7),
    ("Pala Norte", "Cruce B", 2.4, 22, 30, 3.0, 1.8),
    ("Cruce A", "Cruce C", 1.6, 28, 35, 2.5, 1.6),
    ("Cruce A", "Botadero 1", 3.2, 30, 38, 2.6, 1.5),
    ("Cruce B", "Cruce D", 1.7, 24, 32, 2.8, 1.7),
    ("Cruce B", "Pala Sur", 1.5, 20, 28, 3.1, 1.9),
    ("Pala Sur", "Cruce D", 2.0, 23, 31, 2.9, 1.7),
    ("Cruce C", "Botadero 1", 1.9, 27, 36, 2.6, 1.5),
    ("Cruce C", "Chancador", 3.1, 25, 33, 2.8, 1.6),
    ("Cruce D", "Chancador", 2.2, 26, 34, 2.7, 1.6),
    ("Cruce A", "Pala Sur", 2.6, 24, 31, 2.9, 1.8),
]

NODE_COLORS = {
    "pala": "green",
    "cruce": "blue",
    "botadero": "red",
}


def build_graph(closed_roads):
    """Crea una red dirigida con los tramos disponibles."""
    graph = nx.DiGraph()
    for node, data in NODES.items():
        graph.add_node(node, **data)

    for a, b, distance, speed_loaded, speed_empty, fuel_loaded, fuel_empty in ROAD_DATA:
        road_name = f"{a} ↔ {b}"
        if road_name in closed_roads:
            continue

        # La misma conexión se modela en ambos sentidos.
        for start, end in ((a, b), (b, a)):
            graph.add_edge(
                start,
                end,
                distance_km=distance,
                speed_loaded_kmh=speed_loaded,
                speed_empty_kmh=speed_empty,
                fuel_loaded_l_km=fuel_loaded,
                fuel_empty_l_km=fuel_empty,
                road_name=road_name,
            )
    return graph


def path_metrics(graph, path, loaded, fuel_price, truck_payload_t):
    """Calcula distancia, tiempo, combustible, costo y toneladas del viaje."""
    distance = 0.0
    travel_minutes = 0.0
    fuel_liters = 0.0

    for start, end in zip(path[:-1], path[1:]):
        edge = graph[start][end]
        distance += edge["distance_km"]
        speed = edge["speed_loaded_kmh"] if loaded else edge["speed_empty_kmh"]
        fuel_rate = edge["fuel_loaded_l_km"] if loaded else edge["fuel_empty_l_km"]
        travel_minutes += edge["distance_km"] / speed * 60.0
        fuel_liters += edge["distance_km"] * fuel_rate

    return {
        "distance_km": distance,
        "travel_minutes": travel_minutes,
        "fuel_liters": fuel_liters,
        "fuel_cost": fuel_liters * fuel_price,
        "payload_t": truck_payload_t if loaded else 0.0,
    }


def edge_objective(graph, start, end, loaded, w_time, w_fuel, w_distance, fuel_price):
    """Costo adimensional por tramo; permite comparar rutas con varios criterios."""
    edge = graph[start][end]
    speed = edge["speed_loaded_kmh"] if loaded else edge["speed_empty_kmh"]
    fuel_rate = edge["fuel_loaded_l_km"] if loaded else edge["fuel_empty_l_km"]
    minutes = edge["distance_km"] / speed * 60.0
    liters = edge["distance_km"] * fuel_rate

    # Escalas de referencia para que minutos, litros y km sean comparables.
    time_component = minutes / 10.0
    fuel_component = (liters * fuel_price) / 10000.0
    distance_component = edge["distance_km"] / 3.0
    return (
        w_time * time_component
        + w_fuel * fuel_component
        + w_distance * distance_component
    )


def best_path(graph, origin, destination, loaded, weights, fuel_price):
    """Dijkstra usando un costo combinado por tiempo, combustible y distancia."""
    if origin not in graph or destination not in graph:
        return None
    if origin == destination:
        return [origin]

    wt, wf, wd = weights

    def cost(u, v, edge_data):
        return edge_objective(
            graph, u, v, loaded, wt, wf, wd, fuel_price
        )

    try:
        return nx.dijkstra_path(graph, origin, destination, weight=cost)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None


def calculate_cycle(graph, shovel, dump, weights, fuel_price,
                    payload_t, load_minutes, dump_minutes):
    """Calcula viaje cargado, descarga y retorno vacío."""
    loaded_path = best_path(graph, shovel, dump, True, weights, fuel_price)
    if not loaded_path:
        return None

    empty_path = best_path(graph, dump, shovel, False, weights, fuel_price)
    if not empty_path:
        return None

    loaded = path_metrics(graph, loaded_path, True, fuel_price, payload_t)
    empty = path_metrics(graph, empty_path, False, fuel_price, payload_t)

    cycle_minutes = (
        loaded["travel_minutes"] + load_minutes
        + dump_minutes + empty["travel_minutes"]
    )
    total_fuel = loaded["fuel_liters"] + empty["fuel_liters"]
    total_distance = loaded["distance_km"] + empty["distance_km"]
    fuel_cost = total_fuel * fuel_price
    production_tph = payload_t * 60.0 / cycle_minutes if cycle_minutes > 0 else 0.0

    # Puntuación integrada: tiempo de ciclo, costo de combustible y distancia.
    wt, wf, wd = weights
    score = (
        wt * (cycle_minutes / 30.0)
        + wf * (fuel_cost / 100000.0)
        + wd * (total_distance / 10.0)
    )

    return {
        "shovel": shovel,
        "dump": dump,
        "loaded_path": loaded_path,
        "empty_path": empty_path,
        "loaded_distance_km": loaded["distance_km"],
        "empty_distance_km": empty["distance_km"],
        "total_distance_km": total_distance,
        "loaded_minutes": loaded["travel_minutes"],
        "empty_minutes": empty["travel_minutes"],
        "load_minutes": load_minutes,
        "dump_minutes": dump_minutes,
        "cycle_minutes": cycle_minutes,
        "fuel_liters": total_fuel,
        "fuel_cost": fuel_cost,
        "production_tph": production_tph,
        "score": score,
    }


def assign_fleet(graph, shovels, dumps, truck_count, weights, fuel_price,
                 payload_t, load_minutes, dump_minutes, queue_penalty):
    """Asignación heurística: asigna cada camión a la mejor combinación disponible."""
    assignments = []
    shovel_loads = defaultdict(int)

    for truck_num in range(1, truck_count + 1):
        candidates = []
        for shovel in shovels:
            for dump in dumps:
                result = calculate_cycle(
                    graph, shovel, dump, weights, fuel_price,
                    payload_t, load_minutes, dump_minutes
                )
                if result is None:
                    continue
                # Penalización sencilla por camiones ya asignados a la misma pala.
                adjusted_score = result["score"] + shovel_loads[shovel] * queue_penalty
                candidates.append((adjusted_score, result))

        if not candidates:
            break

        candidates.sort(key=lambda item: item[0])
        adjusted_score, chosen = candidates[0]
        chosen = dict(chosen)
        chosen["truck"] = f"Camión {truck_num:02d}"
        chosen["adjusted_score"] = adjusted_score
        assignments.append(chosen)
        shovel_loads[chosen["shovel"]] += 1

    return assignments


def draw_map(graph, assignments, selected_truck=None):
    """Dibuja la red, los puntos y la ruta del camión seleccionado."""
    center = [
        sum(d["lat"] for d in NODES.values()) / len(NODES),
        sum(d["lon"] for d in NODES.values()) / len(NODES),
    ]
    fmap = folium.Map(location=center, zoom_start=14, control_scale=True)

    # Dibujar vías disponibles.
    for u, v, edge in graph.edges(data=True):
        # Solo dibujar una vez por carretera.
        if u > v:
            continue
        p1 = [NODES[u]["lat"], NODES[u]["lon"]]
        p2 = [NODES[v]["lat"], NODES[v]["lon"]]
        folium.PolyLine(
            [p1, p2],
            color="#87929b",
            weight=4,
            opacity=0.75,
            tooltip=f"{u} - {v} | {edge['distance_km']:.1f} km",
        ).add_to(fmap)

    # Dibujar nodos.
    for name, data in NODES.items():
        kind = data["kind"]
        icon_name = "industry" if kind == "pala" else ("dumpster" if kind == "botadero" else "road")
        folium.Marker(
            [data["lat"], data["lon"]],
            tooltip=name,
            popup=f"<b>{name}</b><br>Tipo: {kind}",
            icon=folium.Icon(color=NODE_COLORS[kind], icon=icon_name, prefix="fa"),
        ).add_to(fmap)

    chosen = None
    if selected_truck:
        chosen = next((a for a in assignments if a["truck"] == selected_truck), None)

    if chosen:
        # Ruta cargada en azul y retorno vacío en naranja.
        loaded_coords = [[NODES[n]["lat"], NODES[n]["lon"]] for n in chosen["loaded_path"]]
        empty_coords = [[NODES[n]["lat"], NODES[n]["lon"]] for n in chosen["empty_path"]]
        folium.PolyLine(
            loaded_coords, color="#1565c0", weight=7, opacity=0.95,
            tooltip="Ruta cargada"
        ).add_to(fmap)
        folium.PolyLine(
            empty_coords, color="#ef6c00", weight=6, opacity=0.9,
            dash_array="8, 8", tooltip="Retorno vacío"
        ).add_to(fmap)

    return fmap


# --------------------- PANEL DE CONFIGURACIÓN ---------------------

all_road_names = [f"{a} ↔ {b}" for a, b, *_ in ROAD_DATA]

with st.sidebar:
    st.header("Parámetros operacionales")
    truck_count = st.slider("Cantidad de camiones", 1, 30, 6)
    payload_t = st.number_input("Capacidad útil por camión (t)", 50, 400, 220, step=10)
    load_minutes = st.number_input("Tiempo de carguío (min)", 1.0, 20.0, 4.0, step=0.5)
    dump_minutes = st.number_input("Tiempo de descarga (min)", 0.5, 15.0, 2.0, step=0.5)
    fuel_price = st.number_input("Costo del combustible ($/L)", 100.0, 3000.0, 1200.0, step=50.0)
    queue_penalty = st.slider("Penalización por camiones asignados a una pala", 0.0, 0.30, 0.08, 0.01)
    closed_roads = st.multiselect("Carreteras cerradas", all_road_names, default=[])

    st.subheader("Prioridades de optimización")
    wt = st.slider("Importancia del tiempo", 0, 100, 45)
    wf = st.slider("Importancia del costo de combustible", 0, 100, 35)
    wd = st.slider("Importancia de la distancia", 0, 100, 20)
    weight_sum = wt + wf + wd
    if weight_sum == 0:
        st.warning("Selecciona al menos una prioridad mayor que cero.")
        weights = (1.0, 0.0, 0.0)
    else:
        weights = (wt / weight_sum, wf / weight_sum, wd / weight_sum)
    st.caption("Los pesos se normalizan automáticamente para sumar 100 %.")

graph = build_graph(closed_roads)
shovels = [n for n, d in NODES.items() if d["kind"] == "pala"]
dumps = [n for n, d in NODES.items() if d["kind"] == "botadero"]

assignments = assign_fleet(
    graph, shovels, dumps, truck_count, weights, fuel_price,
    payload_t, load_minutes, dump_minutes, queue_penalty
)

if not assignments:
    st.error("No se encontró una combinación de ruta viable. Revisa las carreteras cerradas.")
    st.stop()

st.subheader("Mapa de la red y rutas recomendadas")
truck_names = [a["truck"] for a in assignments]
selected_truck = st.selectbox("Camión que quieres visualizar", truck_names)
st.caption("Azul: viaje cargado · Naranjo discontinuo: retorno vacío · Gris: red disponible")

fmap = draw_map(graph, assignments, selected_truck)
st_folium(fmap, use_container_width=True, height=560, returned_objects=[])

selected = next(a for a in assignments if a["truck"] == selected_truck)

st.subheader(f"Resultado para {selected_truck}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Tiempo de ciclo", f"{selected['cycle_minutes']:.1f} min")
c2.metric("Distancia por ciclo", f"{selected['total_distance_km']:.2f} km")
c3.metric("Combustible por ciclo", f"{selected['fuel_liters']:.1f} L")
c4.metric("Producción teórica", f"{selected['production_tph']:.0f} t/h")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Viaje cargado**")
    st.write(" → ".join(selected["loaded_path"]))
    st.write(f"Distancia: {selected['loaded_distance_km']:.2f} km")
    st.write(f"Tiempo: {selected['loaded_minutes']:.1f} min")
with col2:
    st.markdown("**Retorno vacío**")
    st.write(" → ".join(selected["empty_path"]))
    st.write(f"Distancia: {selected['empty_distance_km']:.2f} km")
    st.write(f"Tiempo: {selected['empty_minutes']:.1f} min")

st.subheader("Asignación de la flota")
rows = []
for a in assignments:
    rows.append({
        "Camión": a["truck"],
        "Pala": a["shovel"],
        "Destino": a["dump"],
        "Ciclo (min)": round(a["cycle_minutes"], 1),
        "Distancia ciclo (km)": round(a["total_distance_km"], 2),
        "Combustible (L/ciclo)": round(a["fuel_liters"], 1),
        "Costo combustible ($/ciclo)": round(a["fuel_cost"], 0),
        "Producción teórica (t/h)": round(a["production_tph"], 1),
    })
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)

total_tph = sum(a["production_tph"] for a in assignments)
total_fuel = sum(a["fuel_liters"] for a in assignments)
total_fuel_cost = sum(a["fuel_cost"] for a in assignments)
m1, m2, m3 = st.columns(3)
m1.metric("Camiones asignados", len(assignments))
m2.metric("Suma teórica de producción", f"{total_tph:,.0f} t/h")
m3.metric("Combustible estimado por ciclo de cada camión", f"{total_fuel:,.1f} L")

st.caption(
    f"Costo estimado de combustible por ciclo de la flota: ${total_fuel_cost:,.0f}. "
    "La suma de producción es una aproximación y no considera interferencias reales entre camiones."
)

with st.expander("Supuestos y limitaciones importantes"):
    st.markdown(
        """
        - Los nodos, coordenadas, distancias, velocidades y consumos son datos ficticios de demostración.
        - El modelo usa velocidades promedio constantes; no modela pendientes dinámicas, clima, tráfico real ni variación del camino.
        - La asignación de camiones es una heurística codiciosa, no un óptimo global garantizado.
        - La penalización por camiones en una pala es una aproximación simple de congestión.
        - La producción teórica usa capacidad útil dividida por tiempo de ciclo; no descuenta disponibilidad mecánica, utilización, colas reales ni demoras.
        - Antes de usarlo para decisiones operacionales, se debe validar con topografía, despacho mina, seguridad vial y datos reales.
        """
    )
