import torch

from .threshold import threshold

from typing import NamedTuple, Tuple


class CobaLIFState(NamedTuple):
    """State of a conductance based LIF neuron.

    Parameters:
        z (torch.Tensor): recurrent spikes
        v (torch.Tensor): membrane potential
        g_e (torch.Tensor): excitatory input conductance
        g_i (torch.Tensor): inhibitory input conductance
    """

    z: torch.Tensor
    v: torch.Tensor
    g_e: torch.Tensor
    g_i: torch.Tensor


class CobaLIFParameters(NamedTuple):
    """Parameters of conductance based LIF neuron.

    Parameters:
        tau_syn_exc_inv (torch.Tensor): inverse excitatory synaptic input
                                        time constant
        tau_syn_inh_inv (torch.Tensor): inverse inhibitory synaptic input
                                        time constant
        c_m_inv (torch.Tensor): inverse membrane capacitance
        g_l (torch.Tensor): leak conductance
        e_rev_I (torch.Tensor): inhibitory reversal potential
        e_rev_E (torch.Tensor): excitatory reversal potential
        v_rest (torch.Tensor): rest membrane potential
        v_reset (torch.Tensor): reset membrane potential
        v_thresh (torch.Tensor): threshold membrane potential
        method (str): method to determine the spike threshold
                      (relevant for surrogate gradients)
        alpha (float): hyper parameter to use in surrogate gradient computation
    """

    tau_syn_exc_inv: torch.Tensor = torch.as_tensor(1.0 / 5)
    tau_syn_inh_inv: torch.Tensor = torch.as_tensor(1.0 / 5)
    c_m_inv: torch.Tensor = torch.as_tensor(1 / 0.2)
    g_l: torch.Tensor = torch.as_tensor(1 / 20 * 1 / 0.2)
    e_rev_I: torch.Tensor = torch.as_tensor(-100)
    e_rev_E: torch.Tensor = torch.as_tensor(60)
    v_rest: torch.Tensor = torch.as_tensor(-20)
    v_reset: torch.Tensor = torch.as_tensor(-70)
    v_thresh: torch.Tensor = torch.as_tensor(-10)
    method: str = "heaviside"
    alpha: float = 0.0


def coba_lif_step(
    input_tensor: torch.Tensor,
    state: CobaLIFState,
    input_weights: torch.Tensor,
    recurrent_weights: torch.Tensor,
    parameters: CobaLIFParameters = CobaLIFParameters(),
    dt: float = 0.001,
) -> Tuple[torch.Tensor, CobaLIFState]:
    """Euler integration step for a conductance based LIF neuron.

    Parameters:
        input_tensor (torch.Tensor): the input spikes at the current time step
        s (CobaLIFState): current state of the neuron
        input_weights (torch.Tensor): input weights
            (sign determines  contribution to inhibitory / excitatory input)
        recurrent_weights (torch.Tensor): recurrent weights
            (sign determines contribution to inhibitory / excitatory input)
        parameters (CobaLIFParameters): parameters of the neuron
        dt (float): Integration time step
    """
    dg_e = -dt * parameters.tau_syn_exc_inv * state.g_e
    g_e = state.g_e + dg_e
    dg_i = -dt * parameters.tau_syn_inh_inv * state.g_i
    g_i = state.g_i + dg_i

    g_e = g_e + torch.nn.functional.linear(
        input_tensor, torch.nn.functional.relu(input_weights)
    )
    g_i = g_i + torch.nn.functional.linear(
        input_tensor, torch.nn.functional.relu(-input_weights)
    )

    g_e = g_e + torch.nn.functional.linear(
        state.z, torch.nn.functional.relu(recurrent_weights)
    )
    g_i = g_i + torch.nn.functional.linear(
        state.z, torch.nn.functional.relu(-recurrent_weights)
    )

    dv = (
        dt
        * parameters.c_m_inv
        * (
            parameters.g_l * (parameters.v_rest - state.v)
            + g_e * (parameters.e_rev_E - state.v)
            + g_i * (parameters.e_rev_I - state.v)
        )
    )
    v = state.v + dv

    z_new = threshold(v - parameters.v_thresh, parameters.method, parameters.alpha)
    v = (1 - z_new) * v + z_new * parameters.v_reset
    return z_new, CobaLIFState(z_new, v, g_e, g_i)


class CobaLIFFeedForwardState(NamedTuple):
    """State of a conductance based feed forward LIF neuron.

    Parameters:
        v (torch.Tensor): membrane potential
        g_e (torch.Tensor): excitatory input conductance
        g_i (torch.Tensor): inhibitory input conductance
    """

    v: torch.Tensor
    g_e: torch.Tensor
    g_i: torch.Tensor


def coba_lif_feed_forward_step(
    input_tensor: torch.Tensor,
    state: CobaLIFFeedForwardState,
    parameters: CobaLIFParameters = CobaLIFParameters(),
    dt: float = 0.001,
) -> Tuple[torch.Tensor, CobaLIFFeedForwardState]:
    """Euler integration step for a conductance based LIF neuron.

    Parameters:
        input_tensor (torch.Tensor): synaptic input
        state (CobaLIFFeedForwardState): current state of the neuron
        parameters (CobaLIFParameters): parameters of the neuron
        dt (float): Integration time step
    """
    dg_e = -dt * parameters.tau_syn_exc_inv * state.g_e
    g_e = state.g_e + dg_e
    dg_i = -dt * parameters.tau_syn_inh_inv * state.g_i
    g_i = state.g_i + dg_i

    g_e = g_e + torch.nn.functional.relu(input_tensor)
    g_i = g_i + torch.nn.functional.relu(-input_tensor)

    dv = (
        dt
        * parameters.c_m_inv
        * (
            parameters.g_l * (parameters.v_rest - state.v)
            + g_e * (parameters.e_rev_E - state.v)
            + g_i * (parameters.e_rev_I - state.v)
        )
    )
    v = state.v + dv

    z_new = threshold(v - parameters.v_thresh, parameters.method, parameters.alpha)
    v = (1 - z_new) * v + z_new * parameters.v_reset
    return z_new, CobaLIFFeedForwardState(v, g_e, g_i)
