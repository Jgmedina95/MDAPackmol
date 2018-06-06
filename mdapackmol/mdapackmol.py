import MDAnalysis as mda
import subprocess
import warnings


PACKMOL_INP = 'packmol.inp'  # name of .inp file given to packmol
PACKMOL_STRUCTURE_FILES = 'input{}.pdb'
PACKMOL_OUT = 'output.pdb'


class PackmolStructure(object):
    """A Molecule to add to the Packmol system

    Parameters
    ----------
    ag : MDAnalysis.AtomGroup
      the molecule
    number : int
      quantity
    instructions : list
      list of instructions to packmol for this molecule
      eg 'inside box 0. 0. 0. 40. 40. 40.'
      each item in the list should be a single line instruction
    """
    def __init__(self, ag, number, instructions):
        self.ag = ag
        self.number = number
        self.instructions = instructions

    def to_packmol_inp(self, index):
        # creates a single structure section for the packmol.inp file
        output = 'structure {}\n'.format(PACKMOL_STRUCTURE_FILES.format(index))
        output += '  number {}\n'.format(self.number)
        for instruction in self.instructions:
            output += '  ' + instruction + '\n'
        output += 'end structure\n\n'

        return output

    def save_structure(self, index):
        old_resnames = self.ag.residues.resnames.copy()
        self.ag.residues.resnames = 'R{}'.format(index)
        with mda.Writer(PACKMOL_STRUCTURE_FILES.format(index)) as w:
            w.write(self.ag)
        self.ag.residues.resnames = old_resnames


def make_packmol_input(structures, tolerance=None):
    """Convert the call into a Packmol usable input file

    Parameters
    ----------
    structures : list
      list of PackmolStructure objects
    tolerance : float, optional
      minimum distance between molecules, defaults to 2.0
    """
    if tolerance is None:
        tolerance = 2.0
    
    with open(PACKMOL_INP, 'w') as out:
        out.write("# autogenerated packmol input\n\n")

        out.write('tolerance {}\n\n'.format(tolerance))
        out.write('filetype pdb\n\n')

        for i, structure in enumerate(structures):
            out.write(structure.to_packmol_inp(i))
            structure.save_structure(i)
            
        out.write('output {}\n\n'.format(PACKMOL_OUT))


def run_packmol():
    """Run and check that Packmol worked correctly"""
    try:
        p = subprocess.run('packmol < {}'.format(PACKMOL_INP),
                           check=True,
                           shell=True,
                           stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        raise ValueError("Packmol failed with errorcode {}"
                         " and stderr: {}".format(e.returncode, e.stderr))
    else:
        with open('packmol.stdout', 'w') as out:
            out.write(p.stdout.decode())


def load_packmol_output():
    """Parse the output of Packmol"""
    return mda.Universe(PACKMOL_OUT)


def reassign_topology(structures, new):
    """Take Packmol created Universe and add old topology features back in

    Attempts to reassign:
     - resnames

    Parameters
    ----------
    structures : list
      list of Packmol structures used to create the Packmol Universe
    new : Universe
      the raw output of Packmol

    Returns
    -------
    new : Universe
      the raw output modified to best match the templates given to it
    """
    index = 0

    bonds = []
    angles = []
    dihedrals = []
    impropers = []

    # add required attributes
    for attr in ['types', 'names', 'charges', 'masses']:
        if any(hasattr(pms.ag, attr) for pms in structures):
            new.add_TopologyAttr(attr)

            if not all(hasattr(pms.ag, attr) for pms in structures):
                warnings.warn("added attribute which not all templates had")

    while index < len(new.atoms):
        # first atom we haven't dealt with yet
        start = new.atoms[index]
        # the resname was altered to give a hint to what template it was from
        template = structures[int(start.resname[1:])].ag
        # grab atomgroup which matches template
        to_change = new.atoms[index:index + len(template.atoms)]

        # Update residue names
        nres = len(template.residues)
        new.residues[start.resindex:start.resindex + nres].resnames = template.residues.resnames

        # atom attributes
        for attr in ['types', 'names', 'charges', 'masses']:
            if hasattr(template.atoms, attr):
                setattr(to_change, attr, getattr(template.atoms, attr))

        # bonds/angles/torsions
        if hasattr(template, 'bonds'):
            bonds.extend((template.bonds.to_indices() + index).tolist())
        if hasattr(template, 'angles'):
            angles.extend((template.angles.to_indices() + index).tolist())
        if hasattr(template, 'dihedrals'):
            dihedrals.extend((template.dihedrals.to_indices() + index).tolist())
        if hasattr(template, 'impropers'):
            impropers.extend((template.impropers.to_indices() + index).tolist())

        # update the index pointer to be on next unknown atom
        index += len(template.atoms)

    if bonds:
        # convert to tuples for hashability
        bonds = [tuple(val) for val in bonds]
        new.add_TopologyAttr('bonds', values=bonds)
    if angles:
        angles = [tuple(val) for val in bonds]
        new.add_TopologyAttr('angles', values=angles)
    if dihedrals:
        dihedrals = [tuple(val) for val in dihedrals]
        new.add_TopologyAttr('dihedrals', values=dihedrals)
    if impropers:
        impropers = [tuple(val) for val in impropers]
        new.add_TopologyAttr('impropers', values=impropers)

    return new


def packmol(structures, tolerance=None):
    """"Take molecules and settings and create a larger system

    Parameters
    ----------
    structures : list
      list of PackmolStruture objects
    tolerance : float, optional
      Packmol tolerance, defaults to 2.0

    Returns
    -------
    new : MDAnalysis.Universe
      Universe object of the system created by Packmol
    """
    make_packmol_input(structures, tolerance=tolerance)

    run_packmol()

    new = load_packmol_output()

    reassign_topology(structures, new)

    return new
