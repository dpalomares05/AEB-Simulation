# Simulación
HOST = "localhost"
PORT = 2000
TOWN = "Town04"
FIXED_DT = 0.05               # [s]
RUNUP_MAX_TIME = 15.0         # [s]
RUNUP_STABLE_TIME = 1.0       # [s]
RUNUP_SPEED_TOL = 0.5         # [m/s]

START_LOCATION = (9.5, 220.0, 0.5)  # (x, y, z) [m]

TARGET_BLUEPRINT = "vehicle.lincoln.mkz_2020"   # vehículo líder

# Radar (análogo al ARS 548)
RADAR = {
    "range": 300.0,             # [m]
    "min_range": 0.2,           # [m]
    "horizontal_fov": 120.0,    # [°]
    "vertical_fov": 10.0,       # [°]
    "points_per_second": 20000,
    "sensor_tick": FIXED_DT,
    "mount_x_offset": 0.10,     # [m] delante de la defensa
    "mount_z": 0.60,            # [m]
}

# Tiempo máximo sin recibir una entrada
INPUTS = {
    "target_timeout": 0.25,     # SUPUESTO [s]
    "ego_timeout": 0.35,        # SUPUESTO [s]
}

# Percepción
PERCEPTION = {
    "lane_half_width": 1.6,     # [m]
    "min_height": 0.25,         # [m]
    "max_height": 2.5,          # [m]
    "cluster_depth": 1.0,       # [m]
    "ema_alpha": 0.6,
    "hold_frames": 3,
    "ab_alpha": 0.5,            # filtro α-β
    "new_track_jump": 2.5,      # [m]
    "a_lead_limits": (-10.0, 5.0),  # [m/s²]
    "a_lead_alpha": 0.3,
}

AEB_LOGIC = "btn"               # "btn" o "ttc"

AEB_BTN = {
    "tau": 0.30,                # [s]
    "d0": 1.5,                  # [m]
    "btn_fcw": 0.30,
    "ttc_fcw": 2.6,             # [s]
    "d_off": 1.0,               # [m/s²]
    "release_closing_speed": 0.5,  # [m/s]
    "min_ego_speed": 10 / 3.6,  # [m/s]
    "standstill_speed": 0.3,    # [m/s]
    "static_speed": 0.5,        # [m/s]
    "n_conf_moving": 1,
    "n_conf_static": 2,
    "a_ego_limits": (-12.0, 5.0),  # [m/s²]
    "a_ego_alpha": 0.3,
}

PORSCHE_MASS_KG = 2305 + 300    # SUPUESTO
PORSCHE_D_MAX = 6.8             # DOCUMENTADO, dato del equipo [m/s²]

VEHICLES = {
    "porsche": {
        "ego_blueprint": "vehicle.tesla.model3",
        "physics": {            # None = valor de CARLA
            "mass_kg": PORSCHE_MASS_KG,
            "center_of_mass_m": None,
            "drag_coefficient": None,
            "wheel_radius_cm": 36.51,
            "tire_friction": 1.2,
            "max_brake_torque_nm": 1800,
        },
        "carla_brake_map": [(0.0, 0.0), (20.0, 3.66), (40.0, 5.55), (60.0, 6.67), (80.0, 7.69), (100.0, 8.68)],
        "d_max": PORSCHE_D_MAX,
        "radar_pitch_deg": 0.0,  # SUPUESTO
        "btn_on": 0.50,
    },
}
VEHICLE = "porsche"

# Lógica escalonada por TTC
AEB_TTC = {
    "ttc_warning": 2.6,         # [s]
    "ttc_partial": 1.8,         # [s]
    "ttc_full": 1.2,            # [s]
    "partial_demand_pct": 50.0,
    "full_demand_pct": 100.0,
    "min_ego_speed": 1.0,       # [m/s]
    "release_closing_speed": 0.2,  # [m/s]
    "standstill_speed": 0.3,    # [m/s]
}

# Actuador (motor a pasos + tornillo sin fin)
ACTUATOR = {
    "delay_s": 0.10,            # SUPUESTO [s]
    "ramp_full_s": 0.30,        # SUPUESTO, 0 -> 100 % [s]
}

# Freno virtual (solo simulación)
VIRTUAL_BRAKE = {
    "kp": 0.05,
    "ki": 0.80,
    "i_limit": 0.5,
    "meas_alpha": 0.5,
    "ref_tau": 0.20,            # [s]
}

# Conductor virtual (valores del LocalPlanner de CARLA)
LATERAL_PID = {"K_P": 1.95, "K_I": 0.05, "K_D": 0.2, "dt": FIXED_DT}
LONGITUDINAL_PID = {"K_P": 1.0, "K_I": 0.05, "K_D": 0.0, "dt": FIXED_DT}

# Tráfico
TRAFFIC = {
    "blueprints": [
        TARGET_BLUEPRINT, "vehicle.tesla.model3", "vehicle.toyota.prius", "vehicle.audi.a2",
        "vehicle.nissan.patrol_2021", "vehicle.citroen.c3", "vehicle.mini.cooper_s_2021",
        "vehicle.dodge.charger_2020", "vehicle.audi.etron",
    ],
}

# Video
VIDEO = {"width": 1280, "height": 720, "fov": 90}
SCHEMATIC = {"width": 320, "height": 560, "ahead": 70, "behind": 10,
             "lat_min": -6.5, "lat_max": 10.0}
