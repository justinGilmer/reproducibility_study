"""Setup for signac, signac-flow, signac-dashboard for this study."""
# import foyer
import fileinput
import os
import pathlib
import shutil
from glob import glob

import flow
from flow import FlowProject, environments


class Project(flow.FlowProject):
    """Subclass of FlowProject to provide custom methods and attributes."""

    def __init__(self):
        super().__init__()
        current_path = pathlib.Path(os.getcwd()).absolute()
        self.data_dir = current_path.parents[1] / "data"
        self.ff_fn = self.data_dir / "forcefield.xml"


ex = Project.make_group(name="ex")


def get_system(job):
    """Return the system (mbuild filled_box) for a particular job."""
    import sys

    import foyer
    from constrainmol import ConstrainedMolecule

    sys.path.append(Project().root_directory() + "/src/molecules/")
    sys.path.append(Project().root_directory() + "/..")
    from system_builder import construct_system

    system = construct_system(job.sp)
    molecule = get_molecules(job)[0]
    print("project.py has {}".format(molecule))

    system = construct_system(job.sp)
    parmed_molecule = molecule.to_parmed()
    # Apply forcefield from statepoint
    if job.sp.forcefield_name == "trappe-ua":
        ff = foyer.Forcefield(name="trappe-ua")
    elif job.sp.forcefield_name == "oplsaa":
        ff = foyer.Forcefield(name="oplsaa")
    elif job.sp.forcefield_name == "spce":
        ff = foyer.Forcefield(
            name="spce"
        )  # TODO: Make sure this gets applied correctly
    else:
        raise Exception(
            "No forcefield has been applied to this system {}".format(job.id)
        )
    typed_molecule = ff.apply(parmed_molecule)
    print("The typed molecule is {}".format(typed_molecule))
    constrain_mol = ConstrainedMolecule(typed_molecule)

    for box in system:
        if box is None:
            continue
        else:
            for mol in box.children:
                constrain_mol.update_xyz(mol.xyz * 10)  # nm to angstrom
                constrain_mol.solve()
                mol.xyz = constrain_mol.xyz / 10.0  # angstrom to nm

    return system


def get_molecules(job):
    """Return the list of mbuild molecules being used in the job."""
    import sys

    sys.path.append(Project().root_directory() + "/src/molecules/")
    from mbuild.lib.molecules.water import WaterSPC
    from methane_ua import MethaneUA
    from pentane_ua import PentaneUA

    molecule_dict = {
        "methaneUA": MethaneUA(),
        "pentaneUA": PentaneUA(),
        "benzeneUA": None,
        "waterSPC/E": WaterSPC(),
        "ethanolAA": None,
    }
    molecule = molecule_dict[job.sp.molecule]
    return [molecule]


"""Setting progress label"""


@Project.label
def has_fort_files(job):
    """Check if the job has all four equired fort.4 files."""
    return (
        job.isfile("fort.4.melt")
        and job.isfile("fort.4.cool")
        and job.isfile("fort.4.equil")
        and job.isfile("fort.4.prod")
    )


@Project.label
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
def files_ready(job):
    """Check if the keywords in the fort.4 files have been replaced."""
    # Link: https://stackoverflow.com/questions/32749350/check-if-a-string-is-in-a-file-with-python
    job.doc.files_ready = False
    file_names = ["melt", "cool", "equil", "prod"]
    keywords = ["NCHAIN", "LENGTH", "TEMPERATURE", "PRESSURE", "VARIABLES"]
    c = 0
    for name in file_names:
        file_name = job.ws + "/fort.4." + name
        i = 0
        if not job.isfile("fort.4." + name):
            continue
        for i in range(len(keywords)):
            with open(file_name) as myfile:
                if keywords[i] in myfile.read():
                    c += 1
    if c == 0:
        job.doc.files_ready = True

    return job.doc.files_ready


@Project.label
def has_restart_file(job):
    """Check if the job has a restart file."""
    return job.isfile("fort.77")


@Project.label
def has_topmon(job):
    """Check if the job has a topmon (FF) file."""
    return job.isfile("topmon.inp")


@Project.label
def has_fort77maker(job):
    """Check if the job has a fort77maker file (obsolete)."""
    return os.path.isfile(
        Project().root_directory()
        + "/src/engines/mcccs/"
        + "fort77maker_onebox.py"
    )


@Project.label
def equil_replicate_set(job):
    """Check if number of equil replicates done has been set."""
    try:
        return job.doc.equil_replicates_done == 0
    except AttributeError:
        return False


@Project.label
def replicate_set(job):
    """Check if number of replicates for prod has been set."""
    try:
        return job.doc.num_prod_replicates == 4
    except AttributeError:
        return False


@Project.label
def all_prod_replicates_done(job):
    """Check if all prod replicate simulations completed."""
    try:
        a = job.doc.prod_replicates_done
        b = job.doc.num_prod_replicates
        return a >= b
    except (AttributeError, KeyError) as e:
        return False


@Project.label
def melt_finished(job):
    """Check if melt stage is finished."""
    step = "melt"
    run_file = job.ws + "/run.{}".format(step)
    if job.isfile("run.{}".format(step)):
        with open(run_file) as myfile:
            if "Program ended" in myfile.read():
                return True
            else:
                return False


@Project.label
def cool_finished(job):
    """Check if cool stage is finished."""
    step = "cool"
    run_file = job.ws + "/run.{}".format(step)
    if job.isfile("run.{}".format(step)):
        with open(run_file) as myfile:
            if "Program ended" in myfile.read():
                return True
            else:
                return False


@Project.label
def equil_finished(job):
    """Check if equil stage is finished."""
    step = "equil"
    run_file = job.ws + "/run.{}".format(step)
    if job.isfile("run.{}".format(step)):
        with open(run_file) as myfile:
            if "Program ended" in myfile.read():
                return True
            else:
                return False


@Project.label
def prod_finished(job):
    """Check if prod stage is finished."""
    try:

        step = "prod" + str(job.doc.prod_replicates_done)
    except (KeyError, AttributeError):
        step = "prod" + "0"
    run_file = job.ws + "/run.{}".format(step)
    if job.isfile("run.{}".format(step)):
        with open(run_file) as myfile:
            if "Program ended" in myfile.read():
                return True
            else:
                return False


"""Setting up workflow operation"""


@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.post(equil_replicate_set)
def set_equil_replicates(job):
    """Copy the files for simulation from engine_input folder."""
    job.doc.equil_replicates_done = 0


@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.post(replicate_set)
def set_prod_replicates(job):
    """Copy the files for simulation from engine_input folder."""
    job.doc.num_prod_replicates = 4
    job.doc.prod_replicates_done = 0


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.post(has_fort_files)
def copy_files(job):
    """Copy the files for simulation from engine_input folder."""
    for file in glob(
        Project().root_directory()
        + "/src/engine_input/mcccs/{}/fort.4.*".format(job.sp.molecule)
    ):
        shutil.copy(file, job.workspace() + "/")


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.post(has_fort77maker)
def copy_fort77maker(job):
    """Copy fort77maker_onebox.py from root directory to mcccs directory."""
    shutil.copy(
        Project().root_directory()
        + "/src/engine_input/mcccs/fort77maker_onebox.py",
        Project().root_directory() + "/src/engines/mcccs/",
    )


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.post(has_topmon)
def copy_topmon(job):
    """Copy topmon.inp from root directory to mcccs directory."""
    shutil.copy(
        Project().root_directory()
        + "/src/engine_input/mcccs/{}/topmon.inp".format(job.sp.molecule),
        job.workspace() + "/",
    )


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_fort_files)
@Project.post(files_ready)
def replace_keyword_fort_files(job):
    """Replace keywords with the values of the variables defined in signac statepoint."""
    file_names = ["melt", "cool", "equil", "prod"]
    seed = job.sp.replica
    nchain = job.sp.N_liquid
    length = job.sp.box_L_liq * 10  # nm to A
    temperature = job.sp.temperature
    pressure = job.sp.pressure / 1000  # kPa to MPa
    variables = [nchain, length, temperature, pressure, seed]
    keywords = ["NCHAIN", "LENGTH", "TEMPERATURE", "PRESSURE", "SEED"]
    for name in file_names:
        file_name = job.ws + "/fort.4." + name
        i = 0
        for i in range(len(variables)):
            with fileinput.FileInput(file_name, inplace=True) as file:
                for line in file:
                    print(line.replace(keywords[i], str(variables[i])), end="")


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_fort77maker)
@Project.post(has_restart_file)
def make_restart_file(job):
    """Make a fort77 file for the job."""
    from fort77maker_onebox import fort77writer

    molecules = get_molecules(job)
    filled_box = get_system(job)[0]
    print("The filled box in make_restart file is {}".format(filled_box))
    fort77writer(
        molecules,
        filled_box,
        output_file=job.ws + "/fort.77",
        xyz_file=job.ws + "/initial_structure.xyz",
    )


@ex
@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_restart_file)
@Project.pre(has_fort_files)
@Project.pre(has_topmon)
@Project.pre(files_ready)
@Project.post(melt_finished)
def run_melt(job):
    """Run melting stage."""
    from subprocess import PIPE, Popen

    step = "melt"
    """Run the melting stage."""
    print("Running {}".format(step))
    execommand = "/home/rs/group-code/MCCCS-MN-7-20/exe-8-20/src/topmon"
    os.chdir(job.ws)
    shutil.copyfile("fort.4.{}".format(step), "fort.4")
    process = Popen(
        execommand,
        shell=True,
        universal_newlines=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    output, error = process.communicate()
    print(output)
    shutil.move("fort.12", "fort.12.{}".format(step))
    shutil.move("box1config1a.xyz", "box1config1a.xyz.{}".format(step))
    shutil.move("run1a.dat", "run.{}".format(step))
    shutil.copy("config1a.dat", "fort.77")
    shutil.move("config1a.dat", "config1a.dat.{}".format(step))
    shutil.move("box1movie1a.pdb", "box1movie1a.pdb.{}".format(step))
    shutil.move("box1movie1a.xyz", "box1movie1a.xyz.{}".format(step))


@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_restart_file)
@Project.pre(melt_finished)
@Project.post(cool_finished)
def run_cool(job):
    """Run cool stage."""
    from subprocess import PIPE, Popen

    step = "cool"
    """Run the melting stage."""
    print("Running {}".format(step))
    execommand = "/home/rs/group-code/MCCCS-MN-7-20/exe-8-20/src/topmon"
    os.chdir(job.ws)
    shutil.copyfile("fort.4.{}".format(step), "fort.4")
    process = Popen(
        execommand,
        shell=True,
        universal_newlines=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    output, error = process.communicate()
    print(output)
    shutil.move("fort.12", "fort.12.{}".format(step))
    shutil.move("box1config1a.xyz", "box1config1a.xyz.{}".format(step))
    shutil.move("run1a.dat", "run.{}".format(step))
    shutil.copy("config1a.dat", "fort.77")
    shutil.move("config1a.dat", "config1a.dat.{}".format(step))
    shutil.move("box1movie1a.pdb", "box1movie1a.pdb.{}".format(step))
    shutil.move("box1movie1a.xyz", "box1movie1a.xyz.{}".format(step))


@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_restart_file)
@Project.pre(cool_finished)
@Project.post(equil_finished)
@Project.post(system_equilibrated)
def run_equil(job):
    """Run equilibration."""
    from subprocess import PIPE, Popen

    step = "equil"
    """Run the melting stage."""
    print("Running {}".format(step))
    execommand = "/home/rs/group-code/MCCCS-MN-7-20/exe-8-20/src/topmon"
    os.chdir(job.ws)
    shutil.copyfile("fort.4.{}".format(step), "fort.4")
    process = Popen(
        execommand,
        shell=True,
        universal_newlines=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    output, error = process.communicate()
    print(output)
    shutil.move("fort.12", "fort.12.{}".format(step))
    shutil.move("box1config1a.xyz", "box1config1a.xyz.{}".format(step))
    shutil.move("run1a.dat", "run.{}".format(step))
    shutil.copy("config1a.dat", "fort.77")
    shutil.move("config1a.dat", "config1a.dat.{}".format(step))
    shutil.move("box1movie1a.pdb", "box1movie1a.pdb.{}".format(step))
    shutil.move("box1movie1a.xyz", "box1movie1a.xyz.{}".format(step))


@Project.operation
@Project.pre(
    lambda j: j.sp.engine == "mcccs"
    and j.sp.molecule == ("pentaneUA")
    and j.sp.ensemble == "NPT"
)
@Project.pre(has_restart_file)
@Project.pre(equil_finished)
@Project.post(prod_finished)
@Project.post(all_prod_replicates_done)
def run_prod(job):
    """Run production."""
    from subprocess import PIPE, Popen

    job.doc.prod_replicates_done += 1
    replicate = job.doc.prod_replicates_done
    step = "prod" + str(replicate)
    """Run the melting stage."""
    print("Running {}".format(step))
    execommand = "/home/rs/group-code/MCCCS-MN-7-20/exe-8-20/src/topmon"
    os.chdir(job.ws)
    shutil.copyfile("fort.4.prod", "fort.4")
    process = Popen(
        execommand,
        shell=True,
        universal_newlines=True,
        stdin=PIPE,
        stdout=PIPE,
        stderr=PIPE,
    )
    output, error = process.communicate()
    print(output)
    shutil.move("fort.12", "fort.12.{}".format(step))
    shutil.move("box1config1a.xyz", "box1config1a.xyz.{}".format(step))
    shutil.move("run1a.dat", "run.{}".format(step))
    shutil.copy("config1a.dat", "fort.77")
    shutil.move("config1a.dat", "config1a.dat.{}".format(step))
    shutil.move("box1movie1a.pdb", "box1movie1a.pdb.{}".format(step))
    shutil.move("box1movie1a.xyz", "box1movie1a.xyz.{}".format(step))
    print(job.doc.prod_replicates_done)
    print(all_prod_replicates_done(job))
    print(prod_finished(job))


if __name__ == "__main__":
    pr = Project()
    pr.main()
