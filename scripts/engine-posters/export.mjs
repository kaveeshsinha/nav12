// Export exact mesh geometry and instance transforms for the offline poster renderer.
import * as THREE from '../../static/engine/vendor/three.module.min.js';
import {createEngine} from '../../static/engine/engine-model.js';
import fs from 'node:fs';
const engine=createEngine(THREE);engine.group.updateMatrixWorld(true);
const geometries={}, materials={}, objects=[];
engine.group.traverse(o=>{if(!o.isMesh||o.parent===engine.parts.flow)return;
const g=o.geometry,m=o.material;
if(!geometries[g.uuid])geometries[g.uuid]={vertices:Array.from(g.attributes.position.array),normals:Array.from(g.attributes.normal.array),indices:g.index?Array.from(g.index.array):Array.from({length:g.attributes.position.count},(_,i)=>i)};
if(!materials[m.uuid])materials[m.uuid]={color:m.color.toArray(),roughness:m.roughness,metalness:m.metalness,clearcoat:m.clearcoat||0};
if(o.isInstancedMesh){const local=new THREE.Matrix4();for(let i=0;i<o.count;i++){o.getMatrixAt(i,local);objects.push({geometry:g.uuid,material:m.uuid,matrix:new THREE.Matrix4().multiplyMatrices(o.matrixWorld,local).toArray()})}}else objects.push({geometry:g.uuid,material:m.uuid,matrix:o.matrixWorld.toArray()});
});
if (!process.argv[2]) throw new Error('Pass an output JSON path.');
fs.writeFileSync(process.argv[2],JSON.stringify({geometries,materials,objects}));
console.log({geometries:Object.keys(geometries).length,materials:Object.keys(materials).length,objects:objects.length});
