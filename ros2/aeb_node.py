#!/usr/bin/env python3
"""Nodo de ROS 2 del AEB: traduce mensajes y llama a aeb_core.

Plantilla: no se ha probado sobre ROS 2 real. Revisar los POR CONFIRMAR (MDs/README_ros2.md).
target_source: "lider" o "radar".
Arranca en modo sombra: /aeb/brake_demand_pct queda en 0 hasta enable_braking = true.
"""

import math
import os
import sys

import numpy as np
import rclpy
from geometry_msgs.msg import TwistStamped
from radar_msgs.msg import RadarScan
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Imu
from std_msgs.msg import Bool, Float32, String

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config as C
from aeb_core import AebPipeline, Detections, EgoState, LeadState


def scan_to_detections(msg):
    """radar_msgs/RadarScan -> entrada del núcleo. POR CONFIRMAR: signo del Doppler del ARS 548."""
    r = msg.returns
    return Detections(depth=np.array([x.range for x in r], float),
                      azimuth=np.array([x.azimuth for x in r], float),
                      altitude=np.array([x.elevation for x in r], float),
                      velocity=np.array([x.doppler_velocity for x in r], float))


def imu_pitch(msg):
    """Cabeceo [rad] del cuaternión; 0 si el IMU no publica orientación (REP-145). Nariz abajo = negativo."""
    if msg.orientation_covariance[0] == -1.0:
        return 0.0
    q = msg.orientation
    return -math.asin(max(-1.0, min(1.0, 2.0 * (q.w * q.y - q.z * q.x))))   # ROS: +y a la izquierda, nariz abajo = +


class AebNode(Node):
    def __init__(self):
        super().__init__("aeb_node")
        self.declare_parameter("vehicle", C.VEHICLE)
        self.declare_parameter("enable_braking", False)
        self.declare_parameter("target_source", "lider")
        self.declare_parameter("radar_topic", "/radar/detections")   # POR CONFIRMAR: tópico del driver del ARS 548
        self.declare_parameter("lead_distance_topic", "/aeb/lead_distance")   # POR CONFIRMAR: quién publica d
        source = self.get_parameter("target_source").value
        self.pipeline = AebPipeline.from_config(C, vehicle=self.get_parameter("vehicle").value, source=source)
        self.speed = self.accel = self.pitch = None
        self.lead_d = self.lead_v = None
        self.lead_a = float("nan")
        self.override = False

        if source == "radar":
            topic = self.get_parameter("radar_topic").value
            self.create_subscription(RadarScan, topic, self.on_radar, qos_profile_sensor_data)
        else:
            # Distancia de paragolpes a paragolpes; NaN = no hay líder
            self.create_subscription(Float32, self.get_parameter("lead_distance_topic").value, self.on_lead_distance, 10)
            self.create_subscription(TwistStamped, "/v2x/guia/kinematics/speed", self.on_lead_speed, 10)
            self.create_subscription(Imu, "/v2x/guia/imu/accel_set", self.on_lead_imu, 10)
        self.create_subscription(TwistStamped, "/v2x/kinematics/speed", self.on_speed, 10)
        self.create_subscription(Imu, "/v2x/imu/accel_set", self.on_imu, 10)
        # POR CONFIRMAR: de dónde sale la señal de que el conductor retoma el control
        self.create_subscription(Bool, "/aeb/driver_override", self.on_override, 10)
        self.pub_demand = self.create_publisher(Float32, "/aeb/brake_demand_pct", 10)
        self.pub_shadow = self.create_publisher(Float32, "/aeb/shadow_demand_pct", 10)
        self.pub_state = self.create_publisher(String, "/aeb/state", 10)
        self.pub_fault = self.create_publisher(String, "/aeb/fault", 10)
        self.create_timer(C.FIXED_DT, self.on_timer)

    def now_s(self):
        return self.get_clock().now().nanoseconds * 1e-9

    def on_radar(self, msg):
        self.pipeline.on_radar(self.now_s(), scan_to_detections(msg))

    def on_lead_distance(self, msg):
        self.lead_d = msg.data
        self.send_lead()

    def on_lead_speed(self, msg):
        self.lead_v = msg.twist.linear.x    # POR CONFIRMAR: igual que /v2x/kinematics/speed
        self.send_lead()

    def on_lead_imu(self, msg):
        self.lead_a = msg.linear_acceleration.x
        self.send_lead()

    def send_lead(self):
        if self.lead_d is not None and self.lead_v is not None:
            self.pipeline.on_lead(self.now_s(), LeadState(self.lead_d, self.lead_v, self.lead_a))

    def on_speed(self, msg):
        self.speed = msg.twist.linear.x     # POR CONFIRMAR: eje y unidades que publica v2x_fantastico_node
        self.send_ego()

    def on_imu(self, msg):
        self.accel = msg.linear_acceleration.x   # POR CONFIRMAR: ejes del IMU y si incluye la gravedad
        self.pitch = imu_pitch(msg)
        self.send_ego()

    def on_override(self, msg):
        self.override = msg.data
        self.send_ego()

    def send_ego(self):
        if self.speed is not None and self.accel is not None:
            self.pipeline.on_ego(self.now_s(), EgoState(self.speed, self.accel, self.pitch, self.override))

    def on_timer(self):
        out = self.pipeline.tick(self.now_s())
        enabled = self.get_parameter("enable_braking").value
        self.pub_demand.publish(Float32(data=float(out.demand_pct if enabled else 0.0)))
        self.pub_shadow.publish(Float32(data=float(out.demand_pct)))
        self.pub_state.publish(String(data=out.state))
        self.pub_fault.publish(String(data=out.fault))


def main():
    rclpy.init()
    node = AebNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
