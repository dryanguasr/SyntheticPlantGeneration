// Read-only collision replay using the already installed Bullet library.
// No Gazebo server, integration, actuator command, or parameter modification.
// Mesh-selection algorithm reproduces DART v6.13.2 BulletCollisionDetector's
// isConvex threshold convention (not a general convexity certificate):
// https://github.com/dartsim/dart/blob/v6.13.2/dart/collision/bullet/BulletCollisionDetector.cpp
#include <btBulletCollisionCommon.h>
#include <BulletCollision/Gimpact/btGImpactCollisionAlgorithm.h>
#include <BulletCollision/Gimpact/btGImpactShape.h>
#include <array>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

btTransform ReadPose(std::istream &input)
{
  double x,y,z,qx,qy,qz,qw;
  input>>x>>y>>z>>qx>>qy>>qz>>qw;
  return btTransform(btQuaternion(qx,qy,qz,qw),btVector3(x,y,z));
}

struct Pad
{
  std::string side;
  btTransform pose;
  std::vector<btVector3> vertices;
  std::vector<std::array<int,3>> faces;
};

bool DartConvexSelection(const Pad &pad)
{
  // Reproduce the native selection, including its 1 mm distance threshold.
  // Surface geometry is never rewritten or declared convex by this result.
  for(const auto &f:pad.faces)
  {
    const auto &a=pad.vertices[f[0]];
    const auto normal=(pad.vertices[f[1]]-a).cross(pad.vertices[f[2]]-a).normalized();
    const auto reference=(pad.vertices[0]-a).dot(normal);
    for(const auto &vertex:pad.vertices)
    {
      const auto distance=(vertex-a).dot(normal);
      if(std::abs(reference)>.001f && std::abs(distance)>.001f && reference*distance<0)return false;
    }
  }
  return true;
}

void Replay(const Pad &pad,const btTransform &cylinderPose,btScalar radius,
            btScalar length,bool localFrame,bool registerGImpact,double unitScale)
{
  btDefaultCollisionConfiguration configuration;
  btCollisionDispatcher dispatcher(&configuration);
  // DART v6.13.2's dispatcher does NOT register GImpact. The second variant
  // is an explicit isolated algorithm comparison, never a production change.
  if(registerGImpact)btGImpactCollisionAlgorithm::registerAlgorithm(&dispatcher);
  btDbvtBroadphase broadphase;
  btCollisionWorld world(&dispatcher,&broadphase,&configuration);
  btTriangleMesh triangles;
  for(const auto &f:pad.faces)triangles.addTriangle(pad.vertices[f[0]],pad.vertices[f[1]],pad.vertices[f[2]]);
  const bool selectedConvex=DartConvexSelection(pad);
  std::unique_ptr<btCollisionShape> mesh;
  if(selectedConvex)
  {
    auto shape=std::make_unique<btConvexTriangleMeshShape>(&triangles);
    shape->setMargin(0);mesh=std::move(shape);
  }
  else
  {
    auto shape=std::make_unique<btGImpactMeshShape>(&triangles);
    shape->updateBound();mesh=std::move(shape);
  }
  btCylinderShapeZ cylinder(btVector3(radius,radius,length/2));
  btCollisionObject a,b;a.setCollisionShape(mesh.get());b.setCollisionShape(&cylinder);
  const auto shift=localFrame?cylinderPose.inverse():btTransform::getIdentity();
  a.setWorldTransform(shift*pad.pose);b.setWorldTransform(shift*cylinderPose);
  world.addCollisionObject(&a);world.addCollisionObject(&b);
  world.performDiscreteCollisionDetection();
  std::cout<<"{\"side\":\""<<pad.side<<"\",\"local_frame\":"<<(localFrame?"true":"false")
    <<",\"diagnostic_coordinate_scale\":"<<unitScale
    <<",\"registered_gimpact_algorithm\":"<<(registerGImpact?"true":"false")
    <<",\"dart_selects_convex_hull\":"<<(selectedConvex?"true":"false")
    <<",\"mesh_margin_m\":"<<mesh->getMargin()/unitScale<<",\"cylinder_margin_m\":"<<cylinder.getMargin()/unitScale
    <<",\"cylinder_radius_m\":"<<cylinder.getRadius()/unitScale
    <<",\"cylinder_support_x_m\":"<<cylinder.localGetSupportingVertex(btVector3(1,0,0)).x()/unitScale
    <<",\"depths_m\":[";
  bool first=true;
  for(int i=0;i<dispatcher.getNumManifolds();++i)
    for(int j=0;j<dispatcher.getManifoldByIndexInternal(i)->getNumContacts();++j)
    {
      if(!first)std::cout<<",";first=false;
      std::cout<<-dispatcher.getManifoldByIndexInternal(i)->getContactPoint(j).getDistance()/unitScale;
    }
  std::cout<<"]}\n";
  world.removeCollisionObject(&a);world.removeCollisionObject(&b);
}

int main(int argc,char **argv)
{
  if(argc<2 || argc>3){std::cerr<<"Expected verified input and optional diagnostic coordinate scale\n";return 2;}
  const double unitScale=argc==3?std::stod(argv[2]):1.;
  if(!std::isfinite(unitScale)||unitScale<=0)return 2;
  std::ifstream input(argv[1]);double radius,length;int count;
  input>>radius>>length;auto cylinderPose=ReadPose(input);input>>count;
  radius*=unitScale;length*=unitScale;cylinderPose.setOrigin(cylinderPose.getOrigin()*unitScale);
  std::cout<<std::setprecision(17);
  for(int n=0;n<count;++n)
  {
    Pad pad;int vertices,faces;input>>pad.side>>vertices>>faces;pad.pose=ReadPose(input);
    pad.pose.setOrigin(pad.pose.getOrigin()*unitScale);
    for(int i=0;i<vertices;++i){double x,y,z;input>>x>>y>>z;pad.vertices.emplace_back(x*unitScale,y*unitScale,z*unitScale);}
    for(int i=0;i<faces;++i){std::array<int,3> face;input>>face[0]>>face[1]>>face[2];pad.faces.push_back(face);}
    if(!input){std::cerr<<"Incomplete input\n";return 2;}
    for(bool local:{false,true})for(bool registered:{false,true})
      Replay(pad,cylinderPose,radius,length,local,registered,unitScale);
  }
  return 0;
}
