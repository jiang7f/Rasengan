from .provider import Provider, CORE_BASIS_GATES, EXTENDED_BASIS_GATES
from qiskit import QuantumCircuit
from typing import Dict
import numpy as np
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Kraus, SuperOp
from qiskit_aer import AerSimulator
from qiskit.visualization import plot_histogram

# Import from Qiskit Aer noise module
from qiskit_aer.noise import (NoiseModel, QuantumError, ReadoutError,phase_amplitude_damping_error,
    pauli_error, depolarizing_error, thermal_relaxation_error)
from typing import List, Union

from mqt import ddsim

def build_Pauli_noise_model(p_meas: float,p_reset: float, p_gate1: float, single_qubit_gates: List = ['id','sx','x']) -> NoiseModel:
    """
    Build a noise model for a simulator.
    Args:
        p_meas: measurement error probability
        p_reset: reset error probability
        p_gate1: 1-qubit gate error probability
        p_gate2: 2-qubit gate error probability
    """

    # QuantumError objects
    error_reset = pauli_error([('X', p_reset), ('I', 1 - p_reset)])
    error_meas = pauli_error([('X',p_meas), ('I', 1 - p_meas)])
    error_gate1 = pauli_error([('X',p_gate1), ('I', 1 - p_gate1)])
    error_gate2 = error_gate1.tensor(error_gate1)
    # error_gate2 = pauli_error()

    # Add errors to noise model
    noise_bit_flip = NoiseModel()
    noise_bit_flip.add_all_qubit_quantum_error(error_reset, "reset")
    noise_bit_flip.add_all_qubit_quantum_error(error_meas, "measure")
    noise_bit_flip.add_all_qubit_quantum_error(error_gate1, single_qubit_gates)
    noise_bit_flip.add_all_qubit_quantum_error(error_gate2, ["cx"])
    
    return noise_bit_flip 
        
def build_thermal_noise_model(t1: float, t2: float,  single_qubit_gates: List = ['id','sx','x','rx','rz']) -> NoiseModel:
    """
    Build a thermal noise model for a simulator.
    Args:
        t1: relaxation time of first qubit
        t2: relaxation time of second qubit
        gate_time: gate time
    """
   # QuantumError objects
   # Instruction times (in nanoseconds)
    time_g1 = 10
    time_cz = 68
    time_reset =  1560  # 1 microsecond
    time_measure =  1560 # 1 microsecond
    # QuantumError objects
    error_reset = thermal_relaxation_error(t1, t2, time_reset)
    error_measure = thermal_relaxation_error(t1, t2, time_measure)
    error_cz = thermal_relaxation_error(t1, t2,time_cz).expand(thermal_relaxation_error(t1, t2, time_cz))
    error_gate1 = thermal_relaxation_error(t1, t2, time_g1)
    # Add errors to noise model
    noise_thermal = NoiseModel()
    noise_thermal.add_all_qubit_quantum_error(error_gate1, single_qubit_gates)
    noise_thermal.add_all_qubit_quantum_error(error_reset, "reset")
    noise_thermal.add_all_qubit_quantum_error(error_measure, "measure")
    noise_thermal.add_all_qubit_quantum_error(error_cz, ["cz"])
    return noise_thermal 


def build_phase_amplitude_damping_error_model(gamma: float, single_qubit_gates: List = ['id','sx','x','rz']) -> NoiseModel:
    param_amp, param_phase = gamma, gamma
    error_gate1 = phase_amplitude_damping_error(param_amp, param_phase)
    error_gate2 = error_gate1.tensor(error_gate1)
    # Add errors to noise model
    noise_phase_amplitude_damping = NoiseModel()
    noise_phase_amplitude_damping.add_all_qubit_quantum_error(error_gate1, single_qubit_gates)
    noise_phase_amplitude_damping.add_all_qubit_quantum_error(error_gate2, ["cz"])
    return noise_phase_amplitude_damping


def fidelity2lambda_depolar(fidelity,num_qubits=1):
    N = 2**num_qubits
    param = (fidelity*N-1)/(N-1)
    return 1-param

def build_depolarizing_noise_model(
        p_reset = 0.03,
        p_meas = 0.0085,
        p_gate_cz = 0.0037,
        p_gate_single = 2.361e-4
        ):
    from qiskit_aer.noise import NoiseModel
    from qiskit_aer.noise import ReadoutError
    from qiskit_aer.noise import pauli_error
    from qiskit_aer.noise import depolarizing_error
    # 量子错误对象
    error_reset = pauli_error([('X', p_reset), ('I', 1 - p_reset)])
    error_meas = ReadoutError([[1-p_meas,p_meas],[p_meas,1-p_meas]])
    error_gate1 =  depolarizing_error(fidelity2lambda_depolar(1-p_gate_single), 1)
    error_gate_cz = depolarizing_error(fidelity2lambda_depolar(1-p_gate_cz,num_qubits=2), 2)
    # 添加错误到噪声模型
    noisemodel = NoiseModel(basis_gates=['cz', 'id','rx','sx','rz','reset','measure'])
    noisemodel.add_all_qubit_quantum_error(error_gate1, ['id','rx','sx','rz'])
    noisemodel.add_all_qubit_quantum_error(error_reset, "reset")
    noisemodel.add_all_qubit_readout_error(error_meas)
    noisemodel.add_all_qubit_quantum_error(error_gate_cz, ["cz"])
    return  noisemodel
  

class NoiseAerProvider(Provider):
    def __init__(self,**kwargs):
        super().__init__()
        
    def get_counts(self, qc: QuantumCircuit, shots: int) -> Dict:
        # Create noisy simulator backend
        self.sim_noise = AerSimulator(noise_model=self.noise_model, shots=shots,method="tensor_network",device="GPU")
        # Transpile circuit for noisy basis gates
        circ_tnoise = transpile(qc, self.sim_noise)

        # Run and get counts
        result_bit_flip = self.sim_noise.run(circ_tnoise).result()
        counts_bit_flip = result_bit_flip.get_counts(0)
        return counts_bit_flip
    
    def get_probabilities(self, qc: QuantumCircuit, shots: int) -> Dict:
        
        counts = self.get_counts(qc, shots)
        probabilities = {}
        for key, value in counts.items():
            probabilities[key] = value / shots
        return probabilities


    def transpile(self, qc: QuantumCircuit) -> QuantumCircuit:
        self.sim_noise = AerSimulator(noise_model=self.noise_model, method="tensor_network",device="GPU")
        # Transpile circuit for noisy basis gates
        circ_tnoise = transpile(qc, self.sim_noise)
        return circ_tnoise
    
class ThermalNoiseAerProvider(NoiseAerProvider):
    def __init__(self, t1: float, t2: float, **kwargs):
        super().__init__()
        self.noise_model = build_thermal_noise_model(t1, t2)

class BitFlipNoiseAerProvider(NoiseAerProvider):
    def __init__(self, p_meas: float, p_reset: float, p_gate1: float, **kwargs):
        super().__init__()
        self.noise_model = build_Pauli_noise_model(p_meas, p_reset, p_gate1)

class DepolarizingNoiseAerProvider(NoiseAerProvider):
    def __init__(self,p_single_gate,**kwargs):
        super().__init__()
        self.noise_model = build_depolarizing_noise_model(p_gate_cz=10*p_single_gate,p_gate_single=p_single_gate,**kwargs)

class PhaseAmplitudeDampingNoiseAerProvider(NoiseAerProvider):
    def __init__(self, gamma: float, **kwargs):
        super().__init__()
        self.noise_model = build_phase_amplitude_damping_error_model(gamma)



