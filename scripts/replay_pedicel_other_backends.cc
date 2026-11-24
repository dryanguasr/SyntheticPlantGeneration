// Static comparison of the declared pad triangles / analytical cylinder.
// Uses installed FCL / ODE only. This does not reproduce DART's FCL contact
// postprocessing or its 16-sided cylinder tessellation; no native admission.
#include <fcl/fcl.h>
#include <ode/ode.h>
#include <array>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <string>
#include <vector>

using Vec=Eigen::Vector3d;
using Pose=Eigen::Isometry3d;
Pose ReadPose(std::istream &in)
{
  double x,y,z,qx,qy,qz,qw;in>>x>>y>>z>>qx>>qy>>qz>>qw;
  Pose pose=Pose::Identity();pose.linear()=Eigen::Quaterniond(qw,qx,qy,qz).normalized().toRotationMatrix();
  pose.translation()=Vec(x,y,z);return pose;
}
void SetOdePose(dGeomID geom,const Pose &pose)
{
  Eigen::Quaterniond q(pose.linear());dQuaternion rotation={q.w(),q.x(),q.y(),q.z()};
  dGeomSetQuaternion(geom,rotation);const auto &p=pose.translation();dGeomSetPosition(geom,p.x(),p.y(),p.z());
}
void Print(const std::string &backend,const std::string &side,bool local,const std::vector<double> &depths)
{
  std::cout<<"{\"backend\":\""<<backend<<"\",\"side\":\""<<side<<"\",\"local_frame\":"<<(local?"true":"false")
    <<",\"scope\":\"static native-library query, not DART dynamics\",\"depths_m\":[";
  for(size_t i=0;i<depths.size();++i){if(i)std::cout<<",";std::cout<<depths[i];}
  std::cout<<"]}\n";
}
int main(int argc,char **argv)
{
  if(argc!=2)return 2;std::ifstream in(argv[1]);double radius,length;int count;
  in>>radius>>length;const auto cylinderPose=ReadPose(in);in>>count;
  std::cout<<std::setprecision(17);dInitODE2(0);
  for(int n=0;n<count;++n)
  {
    std::string side;int nv,nf;in>>side>>nv>>nf;const auto padPose=ReadPose(in);
    std::vector<Vec> vertices;std::vector<fcl::Triangle> triangles;
    std::vector<double> odeVertices;std::vector<dTriIndex> odeFaces;
    for(int i=0;i<nv;++i){double x,y,z;in>>x>>y>>z;vertices.emplace_back(x,y,z);odeVertices.insert(odeVertices.end(),{x,y,z});}
    for(int i=0;i<nf;++i){int a,b,c;in>>a>>b>>c;triangles.emplace_back(a,b,c);odeFaces.insert(odeFaces.end(),{dTriIndex(a),dTriIndex(b),dTriIndex(c)});}
    if(!in)return 2;
    for(bool local:{false,true})
    {
      const Pose shift=local?cylinderPose.inverse():Pose::Identity();
      const Pose pad=shift*padPose,cylinder=shift*cylinderPose;
      auto mesh=std::make_shared<fcl::BVHModel<fcl::OBBRSSd>>();
      mesh->beginModel();mesh->addSubModel(vertices,triangles);mesh->endModel();
      auto primitive=std::make_shared<fcl::Cylinderd>(radius,length);
      fcl::CollisionObjectd first(mesh,pad),second(primitive,cylinder);
      fcl::CollisionRequestd request;request.enable_contact=true;request.num_max_contacts=128;
      fcl::CollisionResultd result;fcl::collide(&first,&second,request,result);
      std::vector<fcl::Contactd> contacts;result.getContacts(contacts);std::vector<double> depths;
      for(const auto &contact:contacts)depths.push_back(contact.penetration_depth);
      Print("fcl_analytic_cylinder",side,local,depths);
      auto data=dGeomTriMeshDataCreate();
      dGeomTriMeshDataBuildDouble(data,odeVertices.data(),3*sizeof(double),nv,odeFaces.data(),3*nf,3*sizeof(dTriIndex));
      auto meshGeom=dCreateTriMesh(nullptr,data,nullptr,nullptr,nullptr);auto cylinderGeom=dCreateCylinder(nullptr,radius,length);
      SetOdePose(meshGeom,pad);SetOdePose(cylinderGeom,cylinder);
      std::array<dContactGeom,128> odeContacts;int number=dCollide(meshGeom,cylinderGeom,128,odeContacts.data(),sizeof(dContactGeom));
      depths.clear();for(int i=0;i<number;++i)depths.push_back(odeContacts[i].depth);
      Print("ode_analytic_cylinder",side,local,depths);
      dGeomDestroy(meshGeom);dGeomDestroy(cylinderGeom);dGeomTriMeshDataDestroy(data);
    }
  }
  dCloseODE();return 0;
}
