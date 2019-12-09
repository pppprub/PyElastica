import numpy as np
from matplotlib import pyplot as plt
from mpl_toolkits import mplot3d
from elastica.wrappers import BaseSystemCollection, Connections, Constraints, Forcing
from elastica.rod.cosserat_rod import CosseratRod
from elastica.boundary_conditions import OneEndFixedRod, FreeRod, HelicalBucklingBC
from elastica.external_forces import EndpointForces
from elastica.timestepper.symplectic_steppers import PositionVerlet, PEFRL
from elastica.timestepper import integrate
from scipy.linalg import norm

class HelicalBucklingSimulator(BaseSystemCollection, Constraints, Forcing):
    pass


helicalbuckling_sim = HelicalBucklingSimulator()

# setting up test params
n_elem = 200
start = np.zeros((3,))
direction = np.array([0., 0., 1.])
normal = np.array([0., 1., 0.])
base_length = 100.0
base_radius = 0.35
base_area = np.pi * base_radius ** 2
density = 1.0/(base_area)
nu = 0.01
E = 1e6
slack = 3
number_of_rotations = 27
# For shear modulus of 1e4, nu is 99!
poisson_ratio = 99
shear_matrix = np.repeat(1e5 * np.identity((3))[:,:,np.newaxis],n_elem,axis=2)
temp_bend_matrix = np.zeros((3,3))
np.fill_diagonal(temp_bend_matrix,[1.345, 1.345, 0.789])
bend_matrix = np.repeat(temp_bend_matrix[:,:,np.newaxis], n_elem-1, axis=2)

shearable_rod = CosseratRod.straight_rod(
    n_elem,
    start,
    direction,
    normal,
    base_length,
    base_radius,
    density,
    nu,
    E,
    poisson_ratio,
)
# TODO: CosseratRod has to be able to take shear matrix as input, we should change it as done below

shearable_rod.shear_matrix = shear_matrix
shearable_rod.bend_matrix = bend_matrix


helicalbuckling_sim.append(shearable_rod)
helicalbuckling_sim.constrain(shearable_rod).using(HelicalBucklingBC, positions=(0, -1), directors=(0, -1), twisting_time=500, slack=slack, number_of_rotations=number_of_rotations)

helicalbuckling_sim.finalize()
timestepper = PositionVerlet()
shearable_rod.velocity_collection[...,int((n_elem)/2)] += 1e-6# np.array([0, 1e-6, 0.])
# # timestepper = PEFRL()

positions_over_time = []
directors_over_time = []
velocities_over_time = []
final_time = 10500.0
dl = base_length/n_elem
dt = 1e-3*dl
total_steps = int(final_time/dt)
print("Total steps", total_steps)
positions_over_time, directors_over_time, velocities_over_time = integrate(timestepper, helicalbuckling_sim, final_time, total_steps)


plt.figure()
plt.axes(projection="3d")
plt.plot(shearable_rod.position_collection[0, ...], shearable_rod.position_collection[1,...], shearable_rod.position_collection[2,...])
plt.xlim([-10,10])
plt.ylim([-10,10])
plt.show()

# Compute envelope
argumentAcos = np.array([np.dot(shearable_rod.tangents[...,i],np.array([0., 0., 1.0])) for i in range(n_elem)])
argumentAcosClamped = np.amax(np.maximum(-1, np.amin(np.minimum(argumentAcos,1.0))))
phiMax = np.arccos(argumentAcosClamped)
phi = (argumentAcos - np.cos(phiMax))/(1-np.cos(phiMax))

# Plot the envelope
# fig = plt.figure(figsize=(10, 8))
plt.figure()#(figsize=(10, 8))#fig.add_subplot(111)
plt.plot(np.linspace(0.,base_length,n_elem),phi)
plt.show()
# #### Plots for to debugg
# fig = plt.figure(figsize=(10, 8))
# cx = fig.add_subplot(111)
# cx.plot(shearable_rod.position_collection[:,2],shearable_rod.position_collection[:,1])



def envelope(arg_pos):
    """
    Given points, computes the arc length and envelope of the curve
    """
    n_points = arg_pos.shape[1]

    # Computes the direction in which the rod points
    # in our cases it should be the z-axis
    rod_direction = arg_pos[:, -1] - arg_pos[:, 0]
    rod_direction /= norm(rod_direction, ord=2, axis=0)

    # Compute local tangent directions
    tangent_s = np.diff(arg_pos, n=1, axis=-1)  # x_(i+1)-x(i)
    length_s = norm(tangent_s, ord=2, axis=0)
    tangent_s /= length_s

    # Dot product with direction is cos_phi, see RSOS
    cos_phi_s = np.einsum("ij,i->j", tangent_s, rod_direction)

    # Compute phi-max now
    phi = np.arccos(cos_phi_s)
    cos_phi_max = np.cos(np.max(phi))

    # Return envelope and arclength
    envelope = (cos_phi_s - cos_phi_max) / (1.0 - cos_phi_max)
    # -0.5 * length accounts for the element/node business
    arclength = np.cumsum(length_s) - 0.5 * length_s[0]

    return arclength, envelope


def analytical_solution(L):
    """ Gives the analytical solution of the helicalbuckling case
    """
    # Physical parameters, set from the simulation
    B = 1.345
    C = 0.789
    gamma = C / B
    R = 27.0 * 2.0 * np.pi
    d = 0.03
    D = d * L
    nu = 1.0 / gamma - 1.0

    # These are magic constants, but you can obtain them by solving
    # this equation (accoring to matlab syntax)
    # syms x y
    # S = vpasolve([d == sqrt(16/y*(1-x*x/(4*y))), R == x/gamma+4*acos(x/(2*sqrt(y)))], [x, y]);
    # moment = double(S.x); # dimensionless end moment
    # tension = double(S.y); # dimensionless end torque
    # This comes from  Eqs. 14-15 of "Writhing instabilities of twisted rods: from
    # infinite to finite length", 2001
    # We did not want to introduce sympy dependency here, so we decided to hardcode
    # the solutions instead
    moment = 98.541496171190744
    tension = 2.900993205792131e3

    # Compute maximum envelope angle according to Eq. 13 of "Writhing
    # instabilities of twisted rods: from infinite to finite length", 2001
    thetaMax = np.arccos(moment * moment / (2.0 * tension) - 1.0)

    # Compute actual end torque and tension according to "Writhing
    # instabilities of twisted rods: from infinite to finite length", 2001
    M = moment * B / L
    T = tension * B / (L * L)

    # Compute dimensionless load according to Eq. 30 of "Helical and localised
    # buckling in twisted rods: a unified analysis of the symmetric case", 2000
    m = M / np.sqrt(B * T)

    # Setup for analytical curve calculation
    s = np.linspace(-0.5, 0.5, 10000)
    t = T * L * L / (4 * np.pi * np.pi * B)
    mz = M * L / (2 * np.pi * B)
    root = np.sqrt(4 * t - mz * mz)

    # This is the analytical curve computed
    # according to Eqs. 27 and 52 of
    # "Instability and self-contact phenomena in the writhing of clamped rods",
    # 2003
    xs = (
            1.0
            / (2.0 * np.pi * t)
            * root
            * np.sin(mz * np.pi * s)
            / np.cosh(np.pi * s * root)
    )
    ys = (
            -1.0
            / (2.0 * np.pi * t)
            * root
            * np.cos(mz * np.pi * s)
            / np.cosh(np.pi * s * root)
    )
    zs = s - 1.0 / (2.0 * np.pi * t) * root * np.tanh(np.pi * s * root)
    pos = np.vstack((xs, ys, zs)) * L
    return envelope(pos)

phi_analytical_envelope = analytical_solution(base_length)

plt.figure()
plt.plot(phi_analytical_envelope[0],phi_analytical_envelope[1],label='analytical')
plt.plot(np.linspace(0.,base_length,n_elem),phi, label='n=100')
plt.legend()
plt.show()

# class HelicalPhiPlotter():
#     """Plots helical phi """
#
#     # pylint : disable=too-many-arguments
#     def __init__(self):
#     # def __init__(
#     #     self, input_folder, output_folder, save_file, force_flag, display_flag
#     # ):
#         # # pylint : enable=too-many-arguments
#         #
#         # self.file_metadata = [("helix_0100_shape", ".txt", to_rgb("xkcd:bluish"))]
#         #
#         # super(HelicalPhiPlotter, self).__init__(
#         #     input_folder, output_folder, save_file, force_flag, display_flag
#         # )
#
#         # length of rod
#         self.L = 100.0
#
#         # Setting labels here
#         # self.axes[0].set_xlabel("s - L/2")
#         # self.axes[0].set_ylabel("phi")
#         # self.axes[0].set_title("phi vs s")
#
#     def envelope(self, arg_pos):
#         """
#         Given points, computes the arc length and envelope of the curve
#         """
#         n_points = arg_pos.shape[1]
#
#         # Computes the direction in which the rod points
#         # in our cases it should be the z-axis
#         rod_direction = arg_pos[:, -1] - arg_pos[:, 0]
#         rod_direction /= norm(rod_direction, ord=2, axis=0)
#
#         # Compute local tangent directions
#         tangent_s = np.diff(arg_pos, n=1, axis=-1)  # x_(i+1)-x(i)
#         length_s = norm(tangent_s, ord=2, axis=0)
#         tangent_s /= length_s
#
#         # Dot product with direction is cos_phi, see RSOS
#         cos_phi_s = np.einsum("ij,i->j", tangent_s, rod_direction)
#
#         # Compute phi-max now
#         phi = np.arccos(cos_phi_s)
#         cos_phi_max = np.cos(np.max(phi))
#
#         # Return envelope and arclength
#         envelope = (cos_phi_s - cos_phi_max) / (1.0 - cos_phi_max)
#         # -0.5 * length accounts for the element/node business
#         arclength = np.cumsum(length_s) - 0.5 * length_s[0]
#
#         return arclength, envelope
#
#     def analytical_solution(self):
#         """ Gives the analytical solution of the helicalbuckling case
#         """
#         # Physical parameters, set from the simulation
#         B = 1.345
#         C = 0.789
#         gamma = C / B
#         R = 27.0 * 2.0 * np.pi
#         d = 0.03
#         D = d * self.L
#         nu = 1.0 / gamma - 1.0
#
#         # These are magic constants, but you can obtain them by solving
#         # this equation (accoring to matlab syntax)
#         # syms x y
#         # S = vpasolve([d == sqrt(16/y*(1-x*x/(4*y))), R == x/gamma+4*acos(x/(2*sqrt(y)))], [x, y]);
#         # moment = double(S.x); # dimensionless end moment
#         # tension = double(S.y); # dimensionless end torque
#         # This comes from  Eqs. 14-15 of "Writhing instabilities of twisted rods: from
#         # infinite to finite length", 2001
#         # We did not want to introduce sympy dependency here, so we decided to hardcode
#         # the solutions instead
#         moment = 98.541496171190744
#         tension = 2.900993205792131e3
#
#         # Compute maximum envelope angle according to Eq. 13 of "Writhing
#         # instabilities of twisted rods: from infinite to finite length", 2001
#         thetaMax = np.arccos(moment * moment / (2.0 * tension) - 1.0)
#
#         # Compute actual end torque and tension according to "Writhing
#         # instabilities of twisted rods: from infinite to finite length", 2001
#         M = moment * B / self.L
#         T = tension * B / (self.L * self.L)
#
#         # Compute dimensionless load according to Eq. 30 of "Helical and localised
#         # buckling in twisted rods: a unified analysis of the symmetric case", 2000
#         m = M / np.sqrt(B * T)
#
#         # Setup for analytical curve calculation
#         s = np.linspace(-0.5, 0.5, 10000)
#         t = T * self.L * self.L / (4 * np.pi * np.pi * B)
#         mz = M * self.L / (2 * np.pi * B)
#         root = np.sqrt(4 * t - mz * mz)
#
#         # This is the analytical curve computed
#         # according to Eqs. 27 and 52 of
#         # "Instability and self-contact phenomena in the writhing of clamped rods",
#         # 2003
#         xs = (
#             1.0
#             / (2.0 * np.pi * t)
#             * root
#             * np.sin(mz * np.pi * s)
#             / np.cosh(np.pi * s * root)
#         )
#         ys = (
#             -1.0
#             / (2.0 * np.pi * t)
#             * root
#             * np.cos(mz * np.pi * s)
#             / np.cosh(np.pi * s * root)
#         )
#         zs = s - 1.0 / (2.0 * np.pi * t) * root * np.tanh(np.pi * s * root)
#         pos = np.vstack((xs, ys, zs)) * self.L
#         return self.envelope(pos)
#
#     def plot(self, ax, data, color=(31 / 255, 119 / 255, 180 / 255), i_ax=None):
#         """ Plots muscularsnake data
#         """
#         # Muscularsnake data plotted from the second instant
#         # The first instant is just the initialization which is
#         # discarded to give time for the structure to relax (ie contact etc.)
#
#         # Muscularsnake data plotted with reference to the second instant
#         # The first is initial time
#         if ax.lines:
#             pass
#         else:
#             analytical_centerline, analytical_envelope = self.analytical_solution()
#             num_centerline, num_envelope = self.envelope(data)
#
#             ax.plot(
#                 num_centerline - 0.5 * self.L,
#                 num_envelope,
#                 color=color,
#                 marker="o",
#                 linewidth=2,
#                 label="numerical",
#             )
#             ax.plot(
#                 analytical_centerline - 0.5 * self.L,
#                 analytical_envelope,
#                 c="black",
#                 linestyle="--",
#                 linewidth=1,
#                 label="analytical",
#             )
#             ax.legend()
#
#
# a = HelicalPhiPlotter()
# a.analytical_solution(shearable_rod.position_collection)