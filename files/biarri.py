"""
Coding exercise - Biarri optimization
@author: Verena Lenzen
"""

# =============================================================================
# === INITIALIZATION ==========================================================
# =============================================================================


#loading packages
import time, os
import datetime as dt
import pandas as pd
from gurobipy import *


#set working directory
""" 
for simplification purposes I hardcoded the working directory
this should be adjusted in the future
for testing purposes please adjust to your local path 
"""

path = "C:/Users/lenze/Documents/Verena/Work/Applications/Biarri/coding/GitHub/biarri/files"
os.chdir(path)

#log start time
start_time = time.time()

#data assumptions
rest = 12 # minimum rest time between shifts
weight_unassignment = 100
weight_num_shifts = 1


# =============================================================================
# === DATA ====================================================================
# =============================================================================

#reading data
efile = "employees.csv"
employees = pd.read_csv(efile)

sfile = "shifts.csv"
shifts = pd.read_csv(sfile)

#============================================================================

#data manipulation

#employees
employees["Name"] = employees["First Name"] + '_' + employees["Last Name"]
set_empl = set( employees["Name"] ) 
num_empl = len( set_empl )

#shifts
shifts["startdt"] = pd.to_datetime( shifts["Date"] + ' ' + shifts["Start"] )
shifts["enddt"] = pd.to_datetime( shifts["Date"] + ' ' + shifts["End"] )
shifts.loc[(shifts["enddt"] < shifts["startdt"], "enddt")] = shifts["enddt"] + dt.timedelta(days=1)
shifts["date"] = pd.to_datetime( shifts["Date"] )
shifts["duration"] = shifts["enddt"] - shifts["startdt"]
shifts['name'] = shifts['startdt'].dt.strftime('%Y-%m-%d_%H:%M:%S')
num_shifts = shifts.shape[0] 

#shift types
types = shifts.groupby(shifts.columns.tolist()).size().reset_index().rename(columns={0:'number'})
types = types.sort_values(by="startdt").reset_index(drop = True)
num_types = types.shape[0]

"""
simplification: in the data shift types are unique by start datetime
in a more generic implementation one would need to check for all relevant factors
which include duration, break and potentially related skills etc.
"""
set_types = set( types["name"] )
dict_types = {v : i for (i, v) in enumerate(types["name"])} 


#index sets
tuple_e_t = tuplelist()
for e in set_empl:
    for t in set_types:
        tuple_e_t += [(e,t)]
        
tuple_t_t = tuplelist()
for t in set_types:
    for t2 in set_types:
        tuple_t_t += [(t,t2)]

#shift type combination matrix
allowed = []
for t in set_types:
    allowed.append([0]*num_types)
for t in set_types:
    for t2 in set_types:
        allowed[dict_types[t]][dict_types[t2]] = 1 * (                    
            ( types["enddt"][dict_types[t]] + dt.timedelta(hours = rest) < types["startdt"][dict_types[t2]] )
            or
            ( types["enddt"][dict_types[t2]] + dt.timedelta(hours = rest) < types["startdt"][dict_types[t]] )
            )


#t = "2018-06-24 21:00:00"
#t2 = "2018-06-24 05:00:00"
#types["startdt"][dict_types[t]]
#types["startdt"][dict_types[t2]]

# logging
current_time = time.time()
print(' ***** Data reading and modification took ', current_time - start_time, ' seconds.')

# =============================================================================
# === OPTIMIZATION ============================================================
# =============================================================================

# model
m = Model("ShiftAssignment")

# =============================================================================

# variables
v_is_assigned = {} #whether a shift type t is assigned to an employee e
v_unassigned = {} #number of shifts s of shift type t unassigned
v_shift_penalty = {} #number of shifts above ideal maximum

v_is_assigned = m.addVars( tuple_e_t, 
                          vtype = GRB.BINARY, 
                          name = "v_is_assigned" )

v_unassigned = m.addVars( set_types, 
                         vtype = GRB.CONTINUOUS, 
                         lb = 0.0, 
                         name = "v_unassigned" )

v_shift_penalty = m.addVars( set_empl, 
                            vtype = GRB.CONTINUOUS, 
                            lb = 0.0, 
                            name = "v_shift_penalty" )

m.update()

# =============================================================================

# constraints

# shift assignment constraint
m.addConstrs( ( quicksum(v_is_assigned[e,t] for e in set_empl ) + v_unassigned[t] 
                >= types.loc[dict_types[t]]["number"] 
            for t in set_types ), 
            name = "c_assignment" )

# only assign allowed combinations
m.addConstrs( ( v_is_assigned[e,t] + v_is_assigned[e,t2] <= 1 + allowed[dict_types[t]][dict_types[t2]]              
               for e in set_empl for t in set_types for t2 in set_types
               if t != t2
               ),
            name = "c_allowed" )

# constraintS to distribute shift equally across employees
max_shifts = round( num_shifts / num_empl, 0 ) + 1
m.addConstrs( ( quicksum(v_is_assigned[e,t] for t in set_types ) <= max_shifts + v_shift_penalty[e]
            for e in set_empl ),
            name = "c_balancing_max")

min_shifts = round( num_shifts / num_empl, 0 ) - 1
m.addConstrs( ( quicksum(v_is_assigned[e,t] for t in set_types ) >= min_shifts - v_shift_penalty[e]
            for e in set_empl ),
            name = "c_balancing_min")

#debugging constraint forcing unassignment
#m.addConstr( quicksum( v_unassigned[t] for t in set_types ) >= 5, name = "c_debug_unassignment")
                                         
m.update()

# =============================================================================

# objective - minimize number of unassigned shifts 
# and number of shifts away from ideal number of shifts per employee
obj = ( weight_unassignment * quicksum( v_unassigned[t] for t in set_types ) + 
        weight_num_shifts * quicksum( v_shift_penalty[e] for e in set_empl ))
m.setObjective(obj, GRB.MINIMIZE)

# logging
previous_time = current_time
current_time = time.time()
print(' ***** Model creation took ', current_time - previous_time, ' seconds.')


# =============================================================================

# optimization
m.params.mipgap=0.05
m.params.timelimit=300
#m.params.LogToConsole=0 #no Gurobilog in Python

m.write("problem.lp")
m.optimize()
m.write("solution.sol")

# logging
previous_time = current_time
current_time = time.time()
print(' ***** Optimization took ', current_time - previous_time, ' seconds.')

# =============================================================================
# === RESULTS =================================================================
# =============================================================================

#check whether model run was feasible, otherwise print IIS to file
if m.status == GRB.Status.INFEASIBLE:
    m.computeIIS()
    m.write("model_iis.ilp")
    

#if model was feasible retrieve solution and store as schedule
else:
    var_assign = m.getAttr( 'x', v_is_assigned )
    var_unassigned = m.getAttr( 'x', v_unassigned )
    
    schedule = pd.DataFrame(columns=['employee','shift_type'])    
    for (e,t) in tuple_e_t:
        if( var_assign[e,t] > 0.5 ): 
            print( e, ' - ' , t)
            schedule = schedule.append({'employee' : e , 'shift_type' : t} , ignore_index=True)  

    for t in set_types:
        if( var_unassigned[t] > 0.5 ):
            print( var_unassigned[t], ' shifts of type ', t, ' unassigned.' )
            num = int( var_unassigned[t] )
            for i in range(num):
                schedule = schedule.append({'employee' : 'unassigned' , 'shift_type' : t} , ignore_index=True) 
    
    schedule = schedule.sort_values(by=['employee', 'shift_type']).reset_index(drop=True)
    
    schedule.to_csv('schedule.csv', index=False)
    
# logging
end_time = time.time()
print(' ***** Result evaluation took ', end_time - current_time, ' seconds.')
print(' ***** The total runtime was ', end_time - start_time, ' seconds.')


