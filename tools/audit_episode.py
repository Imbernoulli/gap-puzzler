"""Recompute the released-state audit from a saved trajectory and test rejection controls."""
import argparse,copy,json
from pathlib import Path
from puzzler.audit import audit

def main():
    ap=argparse.ArgumentParser();ap.add_argument('episode');ap.add_argument('--out')
    a=ap.parse_args();root=Path(a.episode)
    result=json.loads((root/'result.json').read_text());frames=json.loads((root/'frames.json').read_text())
    original=audit(result,frames)
    shifted=copy.deepcopy(frames)
    for f in shifted:f['poses']['red'][0]+=.008
    held=copy.deepcopy(frames)
    for f in held:
        for h in f['hands']:h[7]=.01
    airborne=copy.deepcopy(frames)
    for f in airborne:
        for pose in f['poses'].values():pose[2]+=.05
    controls={'one_piece_displaced_8mm':audit(result,shifted),
              'grippers_closed':audit(result,held),'board_and_pieces_airborne_50mm':audit(result,airborne)}
    report={'episode':str(root),'original':original,'negative_controls':controls,
            'all_negative_controls_rejected':all(not d['success'] for d in controls.values())}
    dest=Path(a.out) if a.out else root/'audit_recomputed.json'
    dest.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':main()
