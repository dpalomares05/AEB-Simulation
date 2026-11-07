"""Descripción de un ensayo y su traducción al formato del simulador.

Frenada: cuándo y con qué desaceleración frena el líder.
Vehiculo: el líder (separación inicial, velocidad y frenada).
Escenario: el ensayo completo.
"""

import importlib.util
import os
from dataclasses import dataclass, field
from typing import List, Optional

ENSAYOS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ensayos")
KMH = 1 / 3.6


# Clases que usa cada ensayo

@dataclass
class Frenada:
    a_los_s: float                  # instante en que el líder empieza a frenar, desde el inicio [s]
    desaceleracion: float           # [m/s²], positiva
    hasta_kmh: float = 0.0          # velocidad final (0 = hasta detenerse)


@dataclass
class Vehiculo:
    separacion_m: float             # defensa a defensa al inicio del ensayo [m]
    velocidad_kmh: float
    frenada: Optional[Frenada] = None
    carril: float = 0.0             # 0 = mismo carril que el ego (autos centrados)


@dataclass
class Escenario:
    nombre: str
    ego_kmh: float
    lider: Vehiculo
    duracion_s: float = 15.0        # límite de la corrida [s]
    referencia: str = ""            # documento, sección y página
    descripcion: str = ""
    criterio: str = ""


# Formato interno (run_scenario.py y traffic.py)

@dataclass
class Maneuver:
    kind: str                       # "brake"
    t: float                        # [s] instante de inicio
    decel: float = 0.0              # [m/s²]
    v_final: float = 0.0            # [m/s]
    to_lane: int = 0                # (no se usa: cambios de carril)
    duration: float = 0.0           # (no se usa)
    direction: str = ""             # (no se usa: peatones)
    speed: float = 0.0              # (no se usa)


@dataclass
class ActorSpec:
    name: str
    lane: float                     # carril relativo al ego (lateral = lane × ancho de carril)
    gap: float                      # separación inicial defensa a defensa [m]
    speed: float                    # [m/s]
    maneuvers: List[Maneuver] = field(default_factory=list)
    blueprint: Optional[str] = None # None: config.TARGET_BLUEPRINT / TRAFFIC["blueprints"]
    kind: str = "vehiculo"
    roll: float = 0.0


@dataclass
class Scenario:
    name: str
    ego_speed: float                # [m/s]
    actors: List[ActorSpec]
    ego_maneuvers: List[Maneuver] = field(default_factory=list)
    expect_brake: bool = True
    duration: float = 15.0
    description: str = ""
    norma: str = ""
    criterio: str = ""

    @property
    def ego_kmh(self):
        return round(self.ego_speed * 3.6)

    @property
    def run_id(self):
        return f"{self.name}_{self.ego_kmh}kmh"


def a_simulacion(esc):
    """Traduce el Escenario del ensayo al formato interno del simulador."""
    lid = esc.lider
    maniobras = []
    if lid.frenada:
        maniobras.append(Maneuver("brake", lid.frenada.a_los_s, decel=lid.frenada.desaceleracion,
                                  v_final=lid.frenada.hasta_kmh * KMH))
    lider = ActorSpec("lider", lid.carril, lid.separacion_m, lid.velocidad_kmh * KMH, maniobras)
    return Scenario(esc.nombre, esc.ego_kmh * KMH, [lider], duration=esc.duracion_s,
                    description=esc.descripcion, norma=esc.referencia, criterio=esc.criterio)


# Carga de ensayos

def disponibles():
    return sorted(os.path.splitext(f)[0] for f in os.listdir(ENSAYOS_DIR) if f.endswith(".py"))


def cargar(nombre):
    """Carga ensayos/<nombre>.py. Debe definir escenario() y evaluar(impacto_kmh)."""
    path = os.path.join(ENSAYOS_DIR, nombre + ".py")
    spec = importlib.util.spec_from_file_location(f"ensayo_{nombre}", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for fn in ("escenario", "evaluar"):
        if not callable(getattr(mod, fn, None)):
            raise ValueError(f"{path}: falta la función {fn}()")
    return mod


def describir(esc):
    """Lo que se va a simular, en texto, a partir del Escenario ya armado."""
    lid, v = esc.lider, esc.ego_kmh
    out = [f"Ensayo {esc.nombre}, cargado de ensayos\\{esc.nombre}.py",
           f"  Referencia: {esc.referencia}",
           f"  Ensayo:     {esc.descripcion}",
           f"  Ego:        {v:g} km/h",
           f"  Líder:      {lid.velocidad_kmh:g} km/h, {lid.separacion_m:g} m delante (defensa a defensa)"]
    if lid.velocidad_kmh < v:
        out.append(f"              TTC al inicio = {lid.separacion_m / ((v - lid.velocidad_kmh) * KMH):.1f} s")
    if lid.frenada:
        f = lid.frenada
        hasta = "detenerse" if f.hasta_kmh <= 0 else f"{f.hasta_kmh:g} km/h"
        out.append(f"              frena a {f.desaceleracion:g} m/s² desde t = {f.a_los_s:g} s, hasta {hasta}")
    out.append(f"  Criterio:   {esc.criterio}")
    return "\n".join(out)
