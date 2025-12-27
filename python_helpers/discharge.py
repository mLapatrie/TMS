
from math import pi, sqrt

class Resistor:
    def __init__(self, resistance, epc=0, esl=0, esr=0):
        self.resistance = resistance
        self.epc = epc
        self.esl = esl
        self.esr = esr


class Capacitor:
    def __init__(self, capacitance, u_ndc, dv_dt_max, i_pkr, esl=0, esr=0):
        self.capacitance = capacitance
        self.u_ndc = u_ndc
        self.dv_dt_max = dv_dt_max
        self.i_pkr = i_pkr
        self.esl = esl
        self.esr = esr
        

class Inductor:
    def __init__(self, inductance, epc=0, esr=0):
        self.inductance = inductance
        self.epc = epc
        self.esr = esr


class SCR:
    def __init__(self, epc=0, esl=0, esr=0):
        self.epc = 0
        self.esl = 0
        self.esr = 0


class RLC
    def __init__(self, resistor, capacitor, inductor, scr):
        self.resistor = resistor
        self.capacitor = capacitor
        self.inductor = inductor
        self.scr = scr

        self.inductance = self.get_total_inductance()
        self.capacitance = self.get_total_capacitance()
        self.resistance = self.get_total_resistance()

        self.omega_0 = self.get_natural_frequency()
        self.omega = 
    
    def get_total_inductance(self):
        return self.inductor.inductance + \
                self.resistor.esl + \
                self.capacitor.esl + \
                self.scr.esl

    def get_total_capacitance(self):
        return self.capacitor.capacitance + \
                self.resistor.epc + \
                self.inductor.epc + \
                self.scr.epc

    def get_total_resistance(self):
        return self.resistor.resistance + \
                self.capacitor.esr + \
                self.inductor.esr + \
                self.scr.esr

    def get_natural_frequency(self):
        return 1 / sqrt(self.capacitance * self.inductance)

    def get_v_max(self):
        omega = 1/sqrt(self.inductance * self.capacitance)

        omega = omega if omega is not None else 2*pi*freq

        v_max_dv_dt = self.dv_dt_max / omega
        return min(self.u_ndc, v_max_dv_dt)

    def get_i_max(self, inductor, v_max):
        total_inductance = self.esl + inductor.inductance
        total_capacitance = self.capacitance + inductor.epc
        i_max = v_max * sqrt(total_capacitance / total_inductance)
        if i_max > self.i_pkr:
            print("Warning: Peak current is higher than capacitor's rated current")
        return i_max

    def get_di_dt_max(self, inductor, v_max):
        di_dt_max = v_max / inductor.inductance
        return di_dt_max
    

cap = Capacitor(230e-6, 2200, 24e6, 5565, 60e-9, 1.5e-3)
ind = Inductor(12.76e-6, 0, 0)
v_max = cap.get_v_max(inductor=ind)
i_max = cap.get_i_max(inductor=ind, v_max=v_max)
di_dt_max = cap.get_di_dt_max(inductor=ind, v_max=v_max)

print(v_max, i_max, di_dt_max)


