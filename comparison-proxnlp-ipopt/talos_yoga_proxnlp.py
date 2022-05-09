'''
minimization with constraints

Simple example with regularization cost, desired position and position constraints.

min Dq    sum  || q-q0 ||**2  + || diff(position_hand_r(q), position_hand_l(q)) ||**2 +
               || orientation_hand_r(q) - rot_ref_hand_r ||**2 + || orientation_hand_l(q) - rot_ref_hand_l ||**2 +
               || rot_body_y(q) ||**2 + || dist(elbows_(q)) - elboow_ref ||**2
s.t
        q  = integrate(q, Dq)

        lb_com < position_com(q) < ub_com
        pos_and_rot_foot_r(q) == ref_rfeet
        lb_foot_l < foot_l_pos(q) < ub_foot_left
        lb_hand_l < hand_l_pos(q) < ub_hand_l

So the robot should reach a yoga position


Author:
    Alessandro Assirelli

'''
import pinocchio as pin
import pinocchio.casadi as cpin
import casadi
import numpy as np
import example_robot_data as robex
import time

import proxnlp
from proxnlp.manifolds import MultibodyPhaseSpace, VectorSpace
from proxnlp.utils import CasadiFunction, plot_pd_errs

import matplotlib.pyplot as plt
import meshcat

# Load the model both in pinocchio and pinocchio casadi
robot = robex.load('talos')
cmodel = cpin.Model(robot.model)
cdata = cmodel.createData()

model = robot.model
data = model.createData()

q0 = robot.q0
cq0 = casadi.SX(q0)
nq = cmodel.nq
nv = robot.nv
nDq = cmodel.nv
nu = robot.nv - 6

nsteps = 0

xspace = MultibodyPhaseSpace(model)
pb_space = xspace.tangent_space()

viz = pin.visualize.MeshcatVisualizer(robot.model,robot.collision_model,robot.visual_model)

viz.initViewer()
viz.loadViewerModel()
viz.display(robot.q0)
viz.viewer.open()

viewer: meshcat.Visualizer = viz.viewer

cq = casadi.SX.sym('cq', nq, 1)
cDq = casadi.SX.sym('cx', nDq, 1)
R = casadi.SX.sym('R', 3, 3)
R_ref = casadi.SX.sym('R_ref', 3, 3)

# Get the index of the frames which are going to be used
IDX_BASE = cmodel.getFrameId('torso_2_link')
IDX_LF = cmodel.getFrameId('leg_left_6_link')
IDX_RF = cmodel.getFrameId('leg_right_6_link')
IDX_LG = cmodel.getFrameId('gripper_left_base_link')
IDX_RG = cmodel.getFrameId('gripper_right_base_link')
IDX_LE = cmodel.getFrameId('arm_left_4_joint')
IDX_RE = cmodel.getFrameId('arm_right_4_joint')

# This is used in order to go from a configuration and the displacement to the final configuration.
# Why pinocchio.integrate and not simply q = q0 + v*dt? 
# q and v have different dimensions because q contains quaterniions and this can't be done
# So pinocchio.integrate(config, Dq)
integrate = casadi.Function('integrate', [cq, cDq], [ cpin.integrate(cmodel,cq, cDq) ] )

# Casadi function to map joints configuration to COM position                                                        
com_position = casadi.Function('com', [cq], [cpin.centerOfMass(cmodel, cdata, cq)] )

# Compute the forward kinematics and store the data in 'cdata'
# Note that now cdata is filled with symbols, so there is no need to compute the forward kinematics at every variation of q
# Since everything is a symbol, a substituition (which is what casadi functions do) is enough
cpin.framesForwardKinematics(cmodel, cdata, cq)

base_rotation = casadi.Function('com', [cq], [cdata.oMf[IDX_BASE].rotation] )

# Casadi functions can't output a SE3 element, so the oMf matrices are split in rotational and translational components

lf_position = casadi.Function('lf_pos', [cq], [cdata.oMf[IDX_LF].translation])
lf_rotation = casadi.Function('lf_rot', [cq], [cdata.oMf[IDX_LF].rotation])
rf_position = casadi.Function('rf_pos', [cq], [cdata.oMf[IDX_RF].translation])
rf_rotation = casadi.Function('rf_rot', [cq], [cdata.oMf[IDX_RF].rotation])

lg_position = casadi.Function('lg_pos', [cq], [cdata.oMf[IDX_LG].translation])
lg_rotation = casadi.Function('lg_rot', [cq], [cdata.oMf[IDX_LG].rotation])
le_rotation = casadi.Function('le_rot', [cq], [cdata.oMf[IDX_LE].rotation])
le_translation = casadi.Function('le_pos', [cq], [cdata.oMf[IDX_LE].translation])

rg_position = casadi.Function('rg_pos', [cq], [cdata.oMf[IDX_RG].translation])
rg_rotation = casadi.Function('rg_rot', [cq], [cdata.oMf[IDX_RG].rotation])
re_rotation = casadi.Function('re_rot', [cq], [cdata.oMf[IDX_RE].rotation])
re_translation = casadi.Function('re_pos', [cq], [cdata.oMf[IDX_RE].translation])

log = casadi.Function('log', [R, R_ref], [cpin.log3(R.T @ R_ref)])


### ----------------------------------------------------------------------------- ###
### OPTIMIZATION PROBLEM

# Defining weights
parallel_cost = 1
distance_cost = 2.5
straightness_body_cost = 1
elbow_distance_cost = 1
distance_btw_hands = 0.02
left_foot_cost = 0

left_foot_target_z = 0.5

assert xspace.nx == model.nq + model.nv
assert xspace.ndx == model.nv * 2
assert pb_space.nx == model.nv * 2

# Note that here the optimization variables are Dq, not q, and q is obtained by integrating.
# q = q + Dq, where the plus sign is intended as an integrator (because nq is different from nv)
# It is also possible to optimize directly in q, but in that case a constraint must be added in order to have 
# the norm squared of the quaternions = 1
Dxs = casadi.SX.sym("x_opt_0", xspace.ndx)
Dqs = Dxs[: nv]
qs = cpin.integrate(cmodel, cq0, Dqs)


# Cost
cost = 0.
cost += casadi.sumsqr(cpin.difference(cmodel, qs, cq0)) * 0.1


# Distance between the hands
cost += distance_cost * casadi.sumsqr(lg_position(qs) - rg_position(qs) 
                                     - np.array([0, distance_btw_hands, 0]))  

cost += straightness_body_cost * casadi.sumsqr(log(base_rotation(qs), base_rotation(q0)))
cost +=  elbow_distance_cost *casadi.sumsqr(le_translation(qs)[1] - 2) \
        + elbow_distance_cost *casadi.sumsqr(re_translation(qs)[1] + 2)

if left_foot_cost > 0:
    cost += casadi.sumsqr(lf_position(qs)[2] - left_foot_target_z) * left_foot_cost

# Cost on parallelism of the two hands
""" r_ref = pin.utils.rotate('x', 3.14 / 2) # orientation target
cost += parallel_cost * casadi.sumsqr(log(rg_rotation(qs), r_ref))

r_ref = pin.utils.rotate('x', -3.14 / 2) # orientation target
cost += parallel_cost * casadi.sumsqr(log(lg_rotation(qs), r_ref)) """

cost_fun = CasadiFunction(pb_space.nx, pb_space.ndx, cost, Dxs)

# Standing foot
eq_fun_expr = []
eq_fun_expr.append(rf_position(qs) - rf_position(q0))
eq_fun_expr.append(log(rf_rotation(qs), rf_rotation(q0)))

eq_expr = casadi.vertcat(*eq_fun_expr)
eq_st_constr_fun = CasadiFunction(pb_space.nx, pb_space.ndx, eq_expr, Dxs, use_hessian=False)


# Free foot
r_ref = pin.utils.rotate('z', 3.14 / 2) @ pin.utils.rotate('y', 3.14 / 2) # orientation target
t_ref = pin.SE3(r_ref, np.zeros(3))
ineq_fun_expr = []
ineq_fun_expr.append(-lf_position(qs)[2] + left_foot_target_z)
ineq_fun_expr.append(lf_position(qs)[0:2] - 0.1)
ineq_fun_expr.append(-lf_position(qs)[0:2] + 0.05)
ineq_expr = casadi.vertcat(*ineq_fun_expr)
ineq_constr_fun = CasadiFunction(pb_space.nx, pb_space.ndx, ineq_expr, Dxs, use_hessian=False)

eq_fun_expr = []
r_ref = pin.utils.rotate('z', 3.14 / 2) @ pin.utils.rotate('y', 3.14 / 2) # orientation target
eq_fun_expr.append(log(lf_rotation(qs), r_ref))
eq_fun_expr.append(log(lf_rotation(qs), r_ref))
eq_expr = casadi.vertcat(*eq_fun_expr)
eq_sw_constr_fun = CasadiFunction(pb_space.nx, pb_space.ndx, eq_expr, Dxs, use_hessian=False)


eq_fun_expr = []
eq_fun_expr.append(rg_position(qs)[2]-1.2)
eq_fun_expr.append(rg_position(qs)[2] + 1.1)
eq_expr = casadi.vertcat(*eq_fun_expr)
eq_rg_constr_fun = CasadiFunction(pb_space.nx, pb_space.ndx, eq_expr, Dxs, use_hessian=False)

"""opti.subject_to(lf_position(qs)[2] >= 0.4)
opti.subject_to(opti.bounded(0.05, lf_position(qs)[0:2], 0.1))

r_ref = pin.utils.rotate('z', 3.14 / 2) @ pin.utils.rotate('y', 3.14 / 2) # orientation target
opti.subject_to(opti.bounded(-0.0, lf_rotation(qs) - r_ref, 0.0))

# Left hand constraint to be at a certain height
opti.subject_to(opti.bounded(1.1, rg_position(qs)[2], 1.2))
opti.subject_to(opti.bounded(-distance_btw_hands/2, rg_position(qs)[1], 0)) """


### ----------------------------------------------------------------------------- ###
# Solver Setup

cost_fun_ = proxnlp.costs.CostFromFunction(cost_fun)
eq_constr1_ = proxnlp.constraints.create_equality_constraint(eq_st_constr_fun)
eq_constr2_ = proxnlp.constraints.create_equality_constraint(eq_sw_constr_fun)
eq_constr3_ = proxnlp.constraints.create_equality_constraint(eq_rg_constr_fun)
# ineq_constr_ = proxnlp.constraints.create_inequality_constraint(ineq_constr_fun)
ineq_constr_ = proxnlp.constraints.create_equality_constraint(ineq_constr_fun)

constraints = []
constraints.append(eq_constr1_)
constraints.append(eq_constr2_)
constraints.append(ineq_constr_)

prob = proxnlp.Problem(cost_fun_, constraints)

print("No. of variables  :", pb_space.nx)
print("No. of constraints:", prob.total_constraint_dim)
workspace = proxnlp.Workspace(pb_space.nx, pb_space.ndx, prob)
results = proxnlp.Results(pb_space.nx, prob)

callback = proxnlp.helpers.HistoryCallback()
tol = 1e-4
rho_init = 1e-7
mu_init = 0.9

solver = proxnlp.Solver(pb_space, prob, mu_init=mu_init, rho_init=rho_init, tol=tol, verbose=proxnlp.VERYVERBOSE)
solver.register_callback(callback)
solver.maxiters = 1000
solver.use_gauss_newton = True

xu_init = pb_space.neutral()
lams0 = [np.zeros(cs.nr) for cs in constraints]

try:
    flag = solver.solve(workspace, results, xu_init, lams0)
except KeyboardInterrupt as e:
    pass

def plot():
    from proxnlp.utils import plot_pd_errs
    fig, (ax0, ax1) = plt.subplots(1, 2)
    fig: plt.Figure
    ax0: plt.Axes
    fig.set_size_inches(8.4, 4.8)
    prim_errs = callback.storage.prim_infeas
    dual_errs = callback.storage.dual_infeas
    plot_pd_errs(ax0, prim_errs, dual_errs)
    ax0.autoscale_view()

    ax1: plt.Axes
    for i in range(results.numiters):
        if len(callback.storage.ls_alphas[i]) == 0:
            continue
        ax1.plot(callback.storage.ls_alphas[i], callback.storage.ls_values[i])
        print("plotted for it %d" % i)
        break
    plt.tight_layout()
    plt.show()

### -------------------------------------------------------------- ###
# Get results

print("Results struct:\n{}".format(results))
prim_errs = callback.storage.prim_infeas
dual_errs = callback.storage.dual_infeas

dxus_opt = results.xopt
dxs_opt_flat = dxus_opt[:(nsteps + 1) * xspace.nx]
dxs_opt = dxs_opt_flat.reshape(nsteps + 1, -1)
dqs_opt = dxs_opt[:, :model.nv]
dvs_opt = dxs_opt[:, model.nv:]

qs_opt = integrate(q0, dqs_opt).full()

print("Left foot pos :", lf_position(qs_opt).full().flatten())
print("Right foot pos:", rf_position(qs_opt).full().flatten())


plot()

### VISUALIZATION

#viewer.set_cam_target([0., 0.9, 0.])

viz.display(qs_opt)
arr = viewer.get_image()
plt.subplots_adjust(0, 0, 1, 1)
plt.imshow(arr)
plt.axis("off")
plt.show()
