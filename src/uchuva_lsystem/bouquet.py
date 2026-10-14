"""Versioned, morphology-level training heuristic; not a botanical measurement."""
import math

PRESET = "individual_bouquet_crown_v4"


def train_bouquet(plant):
    """Open and lift existing dense branches without adding/removing organs.

    Directions are plant-local, shared by node frames and both interpreters.
    This represents a trained pose, not a simulated string force or growth law.
    """
    if plant.parameter_preset != "individual_dense_crown_v3":
        raise ValueError("Bouquet training requires an unmodified dense v3 plant")

    def visit(axis, parent_azimuth=0.0, attachment_fraction=0.0):
        if axis.order == 0:
            azimuth, inclination, length_factor = 0.0, 0.0, .82
        elif axis.order == 1:
            # Upper attachments open further; lower arms remain close to the base.
            azimuth = axis.azimuth_deg
            inclination = 32.0 + 26.0 * attachment_fraction
            length_factor = .90 + .45 * attachment_fraction
        else:
            # Retain phyllotactic variation within the parent's outward sector.
            offset = ((axis.azimuth_deg + 180.0) % 360.0 - 180.0) * .22
            azimuth = parent_azimuth + offset
            inclination = 48.0 + 8.0 * attachment_fraction
            length_factor = 1.05
        angle, polar = math.radians(azimuth), math.radians(inclination)
        direction = (math.cos(angle)*math.sin(polar),
                     math.sin(angle)*math.sin(polar), math.cos(polar))
        axis.resolved_direction = direction
        axis.training_target_direction = direction
        axis.training_phase = "bouquet_open_and_lift_v4"
        axis.mechanical_deflection_deg = 0.0
        axis.reproductive_load = 0.0
        axis.growth_budget_length_cm *= length_factor
        axis.remaining_budget_length_cm *= length_factor
        for internode in axis.internodes:
            internode.length_cm *= length_factor
            internode.bend_angle_deg = min(1.0, max(-1.0, internode.bend_angle_deg))
            internode.provenance["bouquet_length_factor"] = length_factor
        nodes = {node.id: (i+1)/max(1, len(axis.nodes)) for i,node in enumerate(axis.nodes)}
        for child in axis.child_axes:
            visit(child, azimuth, nodes[child.parent_node_id])

    for root in plant.axes:
        visit(root)
    plant.parameter_preset = PRESET
    plant.metadata["bouquet_training"] = {
        "version": PRESET, "source_preset": "individual_dense_crown_v3",
        "parameter_status": "engineering_heuristic",
        "description": "Shorter leader; progressively outward and upward nodal branches",
        "height_reference_m": 1.8, "height_reference_source": "user_observation",
        "force_simulation": False, "human_validation": "pending",
    }
    return plant
