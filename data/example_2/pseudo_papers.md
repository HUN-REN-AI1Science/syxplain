# Pseudo-papers for the synthetic coating line

FICTITIOUS. These notes are invented for a demonstration of Syxplain. They describe no
real study, and the "coating line" does not exist. They play the role of the published literature on this
type of coating line.

## Note 1. Operating window of the reactor type
The reactor type is operated at precursor partial pressures of 0.1 to 20 Pa, substrate
temperatures of 100 to 300 deg C and carrier flows of 0 to 6 L/min. The chamber is sealed
during deposition, so the humidity of the laboratory air does not reach the film. Films
are produced from 5 to 1000 nm, with grain sizes of 5 to 100 nm.

## Note 2. Chamber pressure
The gauge reads the base pressure plus the partial pressures of precursor and carrier gas:
    chamber_pressure = 15 + precursor + 4 * flow        (Pa)
It is therefore determined by the two settings and is not an independent cause.

## Note 3. Precursor supply
Growth is limited by adsorption of the precursor: the rate rises with the precursor
partial pressure and saturates (Langmuir form, precursor / (K + precursor)); it does not
fall again at high pressure. Carrier gas dilutes the precursor at the surface, so the
rate decreases with flow.

## Note 4. Steady-state growth
After a short start-up the rate is constant during a run, so
    thickness = rate * dep_time                          (nm)
and the rate does not depend on how long the deposition lasts.

## Note 5. Grain growth
Grains coarsen with film thickness and with the annealing temperature, and are refined
by plasma power:
    grain_size = g0 + a * sqrt(thickness) + b * anneal_temp - c * power      (nm)
Annealing changes the film through its grain structure.

## Note 6. Electrical transport
The sheet resistance is the resistivity divided by the thickness,
    sheet_resistance = 10 * rho / thickness              (ohm/sq; rho in micro-ohm cm)
Grain boundaries scatter electrons, so rho rises as grains get smaller and tends to a
finite bulk value for large grains.

## Note 7. Optics
The transmittance at 550 nm decays exponentially with thickness (Beer-Lambert law).
