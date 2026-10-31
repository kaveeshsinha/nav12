#!/usr/bin/env python3
"""Render the original NaV12 model into three WebP fallback assets.

Maintenance-only tool. Requires Node.js and a working EGL OpenGL implementation;
Mesa llvmpipe is sufficient. No live account data or network resources are used.
"""
import json, math, subprocess, tempfile
from pathlib import Path
import moderngl
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'static'/'engine'
with tempfile.TemporaryDirectory(prefix='nav12-posters-') as temporary:
 model_path=Path(temporary)/'model.json'
 subprocess.run(['node', str(Path(__file__).with_name('export.mjs')), str(model_path)], check=True)
 model=json.loads(model_path.read_text())
chunks=[]
for ob in model['objects']:
 g=model['geometries'][ob['geometry']]; m=model['materials'][ob['material']]
 verts=np.array(g['vertices'],dtype=np.float32).reshape(-1,3)
 normals=np.array(g['normals'],dtype=np.float32).reshape(-1,3)
 mat=np.array(ob['matrix'],dtype=np.float32).reshape(4,4,order='F')
 xyz=(np.column_stack([verts,np.ones(len(verts))])@mat.T)[:,:3]
 norm=normals@np.linalg.inv(mat[:3,:3]); norm/=np.maximum(np.linalg.norm(norm,axis=1)[:,None],1e-8)
 ind=np.array(g['indices'],dtype=int)
 props=np.tile(m['color']+[m['roughness'],m['metalness'],m['clearcoat']],(len(ind),1))
 chunks.append(np.column_stack([xyz[ind],norm[ind],props]))
engine=np.concatenate(chunks).astype('f4')
print('Triangles:',len(engine)//3, flush=True)
ctx=moderngl.create_standalone_context(backend='egl')
ctx.enable(moderngl.DEPTH_TEST)
ctx.disable(moderngl.CULL_FACE)
VS='''#version 330
in vec3 p; in vec3 n; in vec3 base; in float rough; in float metal; in float coat;
uniform mat4 vp; uniform mat4 lightVP;
out vec3 world; out vec3 normal; out vec3 color; out float r; out float m; out float c; out vec4 shadowPos;
void main(){ world=p; normal=n; color=base; r=rough; m=metal; c=coat; shadowPos=lightVP*vec4(p,1.);gl_Position=vp*vec4(p,1.);}
'''
FS='''#version 330
in vec3 world;in vec3 normal;in vec3 color;in float r;in float m;in float c;in vec4 shadowPos;
uniform vec3 camera;uniform sampler2DShadow shadowMap;uniform int isFloor;
out vec4 frag;
const float PI=3.14159265359;
float distribution(vec3 N,vec3 H,float rough){float a=rough*rough;float a2=a*a;float nh=max(dot(N,H),0.);float d=nh*nh*(a2-1.)+1.;return a2/(PI*d*d);}
float geom(float nv,float rough){float k=(rough+1.)*(rough+1.)/8.;return nv/(nv*(1.-k)+k);}
vec3 fresnel(float d,vec3 f0){return f0+(1.-f0)*pow(clamp(1.-d,0.,1.),5.);}
float shadow(){vec3 q=shadowPos.xyz/shadowPos.w*.5+.5; if(q.x<0.||q.x>1.||q.y<0.||q.y>1.)return 1.;float s=0.;for(int x=-2;x<=2;x++)for(int y=-2;y<=2;y++)s+=texture(shadowMap,vec3(q.xy+vec2(x,y)/2048.,q.z-.0012));return s/25.;}
vec3 light(vec3 N,vec3 V,vec3 L,vec3 intensity,vec3 f0,float visibility){vec3 H=normalize(V+L);float nl=max(dot(N,L),0.);float nv=max(dot(N,V),.001);vec3 F=fresnel(max(dot(H,V),0.),f0);vec3 spec=distribution(N,H,r)*geom(nv,r)*geom(nl,r)*F/max(4.*nv*nl,.001);vec3 diff=(1.-F)*(1.-m)*color/PI;return (diff+spec)*intensity*nl*visibility;}
vec3 environment(vec3 R,float rough){
 vec3 e=vec3(.09,.105,.12)*(0.6+max(R.y,0.)*.8);
 // Three broad photographic stripboxes; lobe width increases with surface roughness.
 float k=mix(110.,6.,rough*rough);
 e+=vec3(4.9,5.,5.2)*pow(max(dot(R,normalize(vec3(-.35,.8,.62))),0.),k);
 e+=vec3(2.8,3.,3.25)*pow(max(dot(R,normalize(vec3(.8,.25,-.5))),0.),k*.55);
 e+=vec3(2.7,2.8,3.)*pow(max(dot(R,normalize(vec3(-.6,.45,-.6))),0.),k*.75);
 e+=vec3(.7,.75,.85)*pow(max(dot(R,normalize(vec3(.45,.5,.75))),0.),6.);
 return e;
}
vec3 aces(vec3 x){return clamp((x*(2.51*x+.03))/(x*(2.43*x+.59)+.14),0.,1.);}
void main(){vec3 N=normalize(normal);if(!gl_FrontFacing)N=-N;vec3 V=normalize(camera-world);vec3 f0=mix(vec3(.04),color,m);float s=shadow();
 if(isFloor==1){float dist=length(world.xz);float contact=exp(-dist*dist*.19);float sh=1.-(1.-s)*.42;vec3 b=vec3(.03137,.03529,.03921);b*=sh*(1.-contact*.25);b+=vec3(.009,.009,.01)*exp(-dist*dist*.025);frag=vec4(b,1.);return;}
 vec3 result=light(N,V,normalize(vec3(-3.,8.,6.)),vec3(4.6,4.8,5.1),f0,s*.9+.1);
 result+=light(N,V,normalize(vec3(5.,5.,-3.)),vec3(3.2,3.35,3.6),f0,1.);
 result+=light(N,V,normalize(vec3(-5.,2.,-4.)),vec3(1.8,1.95,2.2),f0,1.);
 result+=light(N,V,normalize(vec3(2.,1.,8.)),vec3(.7,.7,.7),f0,1.);
 vec3 R=reflect(-V,N);vec3 F=fresnel(max(dot(N,V),0.),f0);
 result+=environment(R,r)*F*(.8-.3*r);
 result+=color*(1.-m)*(.055+max(N.y,0.)*.13);
 // A controlled coat reflection keeps painted plenums tactile.
 result+=environment(R,.15)*c*.035;
 result*=.86;
 frag=vec4(pow(aces(result),vec3(1./2.2)),1.);
}
'''
prog=ctx.program(vertex_shader=VS,fragment_shader=FS)
vbo=ctx.buffer(engine.tobytes());vao=ctx.vertex_array(prog,[(vbo,'3f 3f 3f 1f 1f 1f','p','n','base','rough','metal','coat')])
depth_prog=ctx.program(vertex_shader='''#version 330
in vec3 p;uniform mat4 lightVP;void main(){gl_Position=lightVP*vec4(p,1.);}''',fragment_shader='''#version 330
void main(){}''')
depth_vao=ctx.vertex_array(depth_prog,[(vbo,'3f 36x','p')])
def normalize(v):return v/np.linalg.norm(v)
def lookat(eye,target,up=np.array([0.,1.,0.])):
 eye=np.array(eye,dtype=float);target=np.array(target,dtype=float);z=normalize(eye-target);x=normalize(np.cross(up,z));y=np.cross(z,x);m=np.eye(4);m[:3,:3]=np.array([x,y,z]);m[:3,3]=-m[:3,:3]@eye;return m
lightvp=np.array([[1/8,0,0,0],[0,1/8,0,0],[0,0,-2/35,-1],[0,0,0,1]],dtype=float)@lookat([-7,16,12],[0,0,0])
# Standard orthographic depth range from 0 to 35.
depth=ctx.depth_texture((2048,2048));depth.compare_func='<=';depth.repeat_x=False;depth.repeat_y=False
shadowfb=ctx.framebuffer(depth_attachment=depth);shadowfb.use();ctx.viewport=(0,0,2048,2048);shadowfb.clear(depth=1.)
depth_prog['lightVP'].write(lightvp.T.astype('f4').tobytes());depth_vao.render()
depth.use(location=0);prog['shadowMap'].value=0;prog['lightVP'].write(lightvp.T.astype('f4').tobytes())
# The floor meets the sump with a quiet contact shadow and no visible horizon.
p=[[-70,-2.03,-70],[70,-2.03,-70],[70,-2.03,70],[-70,-2.03,-70],[70,-2.03,70],[-70,-2.03,70]]
floor=np.column_stack([p,np.tile([0,1,0,.0025,.003,.0035,.75,.1,0],(6,1))]).astype('f4')
fvbo=ctx.buffer(floor.tobytes());fvao=ctx.vertex_array(prog,[(fvbo,'3f 3f 3f 1f 1f 1f','p','n','base','rough','metal','coat')])
def render(name,w,h,eye,fov=32,shift=(0,0),target=(0,.05,0)):
 scale=2;rw,rh=w*scale,h*scale;aspect=rw/rh;f=1/math.tan(math.radians(fov/2));near=.1;far=100
 projection=np.array([[f/aspect,0,-shift[0],0],[0,f,-shift[1],0],[0,0,(far+near)/(near-far),2*far*near/(near-far)],[0,0,-1,0]],dtype='f4')
 vp=projection@lookat(eye,target)
 color=ctx.texture((rw,rh),4);z=ctx.depth_renderbuffer((rw,rh));fb=ctx.framebuffer(color_attachments=[color],depth_attachment=z);fb.use();ctx.viewport=(0,0,rw,rh);fb.clear(8/255,9/255,10/255,1.,depth=1.)
 prog['vp'].write(vp.T.astype('f4').tobytes());prog['camera'].value=tuple(eye)
 prog['isFloor'].value=1;fvao.render();prog['isFloor'].value=0;vao.render()
 img=Image.frombytes('RGBA',(rw,rh),fb.read(components=4)).transpose(Image.Transpose.FLIP_TOP_BOTTOM).convert('RGB').resize((w,h),Image.Resampling.LANCZOS)
 img.save(OUT/name,'WEBP',quality=88,method=6)
 fb.release();color.release();z.release();print(name, (OUT/name).stat().st_size,flush=True)
render('engine-poster.webp',1600,1000,[10.1,6.6,11.5],32,(.43,.03))
render('engine-poster-mobile.webp',800,1200,[11.5,8.,13.],40,(0,-.27))
render('engine-teaser.webp',1200,900,[10.2,6.5,11.5],30,(0,.0))
