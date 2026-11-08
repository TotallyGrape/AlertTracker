type Report = { owner: { toHexString():string }; status:string; createdAt:{ microsSinceUnixEpoch:bigint }; latitude:number; longitude:number; helpType:string; peopleAffected:number };
export function aggregateCommunity(rows: Iterable<Report>, at:bigint) {
  const groups=new Map<string,Map<string,{help:string;people:number;created:bigint}>>();
  for (const row of rows) {
    if (row.status!=='submitted' || row.createdAt.microsSinceUnixEpoch+86_400_000_000n<=at) continue;
    const key=`${Math.floor(row.latitude/.05)}:${Math.floor(row.longitude/.06)}`;
    if (!groups.has(key)) groups.set(key,new Map());
    const owners=groups.get(key)!, owner=row.owner.toHexString();
    if (!owners.has(owner) || owners.get(owner)!.created<row.createdAt.microsSinceUnixEpoch)
      owners.set(owner,{help:row.helpType,people:row.peopleAffected,created:row.createdAt.microsSinceUnixEpoch});
  }
  return [...groups.entries()].filter(([,owners])=>owners.size>=2).map(([cell,owners])=>{
    const [lat,lon]=cell.split(':').map(Number), types:Record<string,number>={};
    let people=0;
    for (const row of owners.values()) { types[row.help]=(types[row.help]??0)+1; people+=row.people; }
    return {id:cell,latitude:Number(((lat+.5)*.05).toFixed(3)),longitude:Number(((lon+.5)*.06).toFixed(3)),report_count:owners.size,people_reported:people,help_types:types};
  });
}
