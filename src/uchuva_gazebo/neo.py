"""Approximate Neo envelope and simulated multicopter, not DJI firmware."""
import math
import xml.etree.ElementTree as ET
from .field import element as e, box, material, numbers

VERSION = 'neo-flight/0.1'
LENGTH, WIDTH, HEIGHT, MASS = .130, .157, .0485, .135
SOURCE = 'https://www.dji.com/neo/specs'
FORCE_CONSTANT = 1e-7  # engineering_heuristic, not measured DJI propulsion


def inertial(link, mass, size):
    inertia=e(link,'inertial'); e(inertia,'mass',mass)
    tensor=e(inertia,'inertia'); x,y,z=size
    for key,value in {'ixx':mass*(y*y+z*z)/12,'iyy':mass*(x*x+z*z)/12,
                      'izz':mass*(x*x+y*y)/12,'ixy':0,'ixz':0,'iyz':0}.items(): e(tensor,key,value)


def plugin(model, filename, name, values):
    node=e(model,'plugin',filename=f'gz-sim-{filename}-system',name=f'gz::sim::systems::{name}')
    for key,value in values.items(): e(node,key,value)
    return node


def sensor(link, name, pose, width=1280,height=720):
    node=e(link,'sensor',name=name,type='camera'); e(node,'pose',numbers(pose))
    e(node,'always_on','true'); e(node,'update_rate',15); e(node,'topic',f'/neo/{name}')
    cam=e(node,'camera'); e(cam,'horizontal_fov',math.pi/2)
    image=e(cam,'image'); e(image,'width',width); e(image,'height',height); e(image,'format','R8G8B8')
    clip=e(cam,'clip'); e(clip,'near',.01); e(clip,'far',100)


def neo_model(start=(-5.2,-5.6,.08), cameras=True):
    model=ET.Element('model',name='neo_approx'); e(model,'pose',numbers((*start,0,0,0)))
    base=e(model,'link',name='base_link')
    inertial(base,MASS-.004,(LENGTH,WIDTH,HEIGHT))
    box(base,'body',(0,0,0),(.095,.044,HEIGHT),(.62,.65,.66,1))
    box(base,'battery',(-.019,0,.018),(.046,.041,.01),(.32,.34,.35,1))
    box(base,'camera',(.056,0,-.006),(.018,.023,.021),(.04,.045,.05,1))
    box(base,'envelope',(0,0,0),(LENGTH,WIDTH,HEIGHT),collision=True)
    rotors=[]
    for index,(x,y,spin) in enumerate(((.0315,.045,1),(-.0315,-.045,1),(.0315,-.045,-1),(-.0315,.045,-1))):
        # Open guard ring, approximated by short tangential bars within envelope.
        for segment in range(24):
            a=2*math.pi*segment/24
            visual=box(base,f'guard_{index}_{segment}',(x+.0315*math.cos(a),y+.0315*math.sin(a),.009),
                       (.0083,.003,.008),(.54,.57,.58,1))
            visual.find('pose').text=numbers((x+.0315*math.cos(a),y+.0315*math.sin(a),.009,0,0,a+math.pi/2))
        link=e(model,'link',name=f'rotor_{index}'); e(link,'pose',numbers((x,y,.01,0,0,0)))
        inertial(link,.001,(.055,.008,.003))
        box(link,f'propeller_{index}',(0,0,0),(.057,.006,.002),(.13,.14,.15,1))
        joint=e(model,'joint',name=f'rotor_{index}_joint',type='revolute')
        e(joint,'parent','base_link'); e(joint,'child',f'rotor_{index}')
        axis=e(joint,'axis'); e(axis,'xyz','0 0 1')
        limit=e(axis,'limit'); e(limit,'lower',-1e16); e(limit,'upper',1e16)
        plugin(model,'multicopter-motor-model','MulticopterMotorModel',{
            'robotNamespace':'neo','jointName':f'rotor_{index}_joint','linkName':f'rotor_{index}',
            'turningDirection':'ccw' if spin==1 else 'cw','timeConstantUp':.0125,'timeConstantDown':.025,
            'maxRotVelocity':3000,'motorConstant':FORCE_CONSTANT,'momentConstant':.006,
            'commandSubTopic':'motor_speed','actuator_number':index,'rotorDragCoefficient':1e-6,
            'rollingMomentCoefficient':1e-8,'rotorVelocitySlowdownSim':20,'motorType':'velocity'})
        rotors.append((index,spin))
    control=plugin(model,'multicopter-control','MulticopterVelocityControl',{
        'robotNamespace':'neo','commandSubTopic':'cmd_vel','enableSubTopic':'enable',
        'comLinkName':'base_link','velocityGain':'3 3 4','attitudeGain':'.008 .008 .003',
        'angularRateGain':'.001 .001 .0005','maximumLinearAcceleration':'1 1 1',
        'maximumLinearVelocity':'1.2 1.2 .7','maximumAngularVelocity':'1 1 .8'})
    config=e(control,'rotorConfiguration')
    for index,spin in rotors:
        rotor=e(config,'rotor'); e(rotor,'jointName',f'rotor_{index}_joint')
        e(rotor,'forceConstant',FORCE_CONSTANT); e(rotor,'momentConstant',.006); e(rotor,'direction',spin)
    plugin(model,'odometry-publisher','OdometryPublisher',{'dimensions':3,'odom_publish_frequency':30,
        'odom_topic':'/neo/odometry'})
    if cameras:
        sensor(base,'onboard',(.068,0,.005,0,.65,0))
        sensor(base,'chase',(-.70,0,.38,0,.38,0))
    return model


def mission_waypoints():
    """Above-trellis sweep of all six rows, then return and descend outside crop."""
    points=[{'position':[-5.2,-5.6,3.4],'yaw':0,'phase':'takeoff'}]
    for row in range(6):
        y=(row-2.5)*1.8
        left,right=(-4.4,4.4) if row%2==0 else (4.4,-4.4)
        yaw=0 if row%2==0 else math.pi
        points.extend([{'position':[left,y,3.4],'yaw':yaw,'phase':f'row_{row}_entry'},
                       {'position':[right,y,3.4],'yaw':yaw,'phase':f'row_{row}_exit'}])
    points.extend([{'position':[-5.2,5.6,3.4],'yaw':-math.pi/2,'phase':'return_outside'},
                   {'position':[-5.2,-5.6,3.4],'yaw':-math.pi/2,'phase':'return_home'},
                   {'position':[-5.2,-5.6,.10],'yaw':0,'phase':'descent'}])
    return points
