from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import os
import subprocess
import uuid
import logging
import re
from typing import Dict, Optional, List, Any, Union
import shutil

app = FastAPI(title="PBNSolve API", description="API for solving nonogram (paint-by-numbers) puzzles")

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporary files directory configuration
UPLOAD_FOLDER = '/tmp/pbnsolve'
MAX_FILE_SIZE = 1 * 1024 * 1024  # 1MB

# Supported file formats
ALLOWED_FORMATS = {
    'xml': 'xml',
    'non': 'non',
    'mk': 'mk',
    'g': 'g',
    'nin': 'nin',
    'cwd': 'cwd',
    'lp': 'lp',
    'pbm': 'pbm'
}

# Pydantic model for pbnsolve options
class PbnsolveOptions(BaseModel):
    check_uniqueness: bool = False
    check_solution: bool = False
    terse: bool = False
    statistics: bool = False
    http_mode: bool = False
    output_dump: bool = False
    
    # Algorithms
    use_line_solving: bool = True
    use_exhaust: bool = True
    use_contradiction: bool = False
    use_guessing: bool = True
    use_probing: bool = True
    use_merge_probe: bool = False
    use_caching: bool = True
    
    # Additional parameters
    contradiction_depth: int = 2
    cpu_limit: int = 0
    start_solution: int = 0
    puzzle_index: int = 1
    
    # Debug parameters
    hint_log: bool = False
    hint_log_n: int = 10
    
    # Algorithm parameters
    scoring_rule: Optional[int] = None
    probing_level: Optional[int] = None


# Pydantic model for solver response
class SolverResponse(BaseModel):
    status: str
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    return_code: Optional[int] = None
    solution: Optional[str] = None
    solution_type: Optional[str] = None 

def create_temp_directory():
    """Creates temporary directory if it doesn't exist"""
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def is_allowed_file_format(file_format: str) -> bool:
    """Checks if the file format is supported"""
    return file_format.lower() in ALLOWED_FORMATS

def cleanup_temp_file(file_path: str):
    """Function to remove temporary file"""
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"Removed temporary file: {file_path}")
    except Exception as e:
        logger.error(f"Error removing temporary file: {str(e)}")

def preprocess_xml_file(file_path: str):
    """Processes XML file to remove DTD issues"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
            
        # Remove external DTD references
        modified_content = re.sub(r'<!DOCTYPE[^>]*>', '', content)
        
        with open(file_path, 'w') as f:
            f.write(modified_content)
            
        logger.info(f"Preprocessed XML file: {file_path}")
    except Exception as e:
        logger.error(f"Error preprocessing XML file: {str(e)}")

def create_pbnsolve_args(options: PbnsolveOptions, file_format: str, file_path: str) -> list:
    """Creates argument list for pbnsolve based on provided options"""
    args = ['pbnsolve']
    
    # Basic settings
    if options.check_uniqueness:
        args.append('-u')
    if options.check_solution:
        args.append('-c')
    if options.terse:
        args.append('-b')
    if options.statistics:
        args.append('-t')
    if options.http_mode:
        args.append('-h')
    if options.output_dump:
        args.append('-o')
        
    # Algorithm settings - using -a with appropriate letters
    alg_flags = ""
    if options.use_line_solving:
        alg_flags += "L"
    if options.use_exhaust:
        alg_flags += "E"
    if options.use_contradiction:
        alg_flags += "C"
    if options.use_guessing:
        alg_flags += "G"
    if options.use_probing:
        alg_flags += "P"
    if options.use_merge_probe:
        alg_flags += "M"
    if options.use_caching:
        alg_flags += "H"
    
    if alg_flags:
        args.append(f"-a{alg_flags}")
        
    # Additional numeric parameters
    if options.contradiction_depth != 2:
        args.append(f"-d{options.contradiction_depth}")
    if options.cpu_limit > 0:
        args.append(f"-x{options.cpu_limit}")
    if options.start_solution > 0:
        args.append(f"-s{options.start_solution}")
    if options.puzzle_index > 1:
        args.append(f"-n{options.puzzle_index}")
    
    # Hint log
    if options.hint_log:
        if options.hint_log_n != 10:
            args.append(f"-m{options.hint_log_n}")
        else:
            args.append("-m")
    
    # Specific algorithm parameters
    if options.scoring_rule is not None:
        args.append(f"-aG{options.scoring_rule}")
    if options.probing_level is not None:
        args.append(f"-aP{options.probing_level}")
    
    # Set file format
    args.extend(["-f", ALLOWED_FORMATS[file_format.lower()]])
    
    # Add file path
    args.append(file_path)
    
    return args

def parse_pbnsolve_output(stdout: str, stderr: str, return_code: int) -> dict:
    """Parses pbnsolve output and returns a structured result with original status"""
    result = {
        "status": "success" if return_code == 0 else "error",
        "stdout": stdout,
        "stderr": stderr,
        "return_code": return_code,
        "solution": None,
        "solution_type": None
    }
    
    # Extract solution type
    solution_type_patterns = [
        (r"UNIQUE LINE SOLUTION:", "UNIQUE_LINE_SOLUTION"),
        (r"UNIQUE DEPTH-\d+ SOLUTION:", "UNIQUE_DEPTH_SOLUTION"),
        (r"UNIQUE SOLUTION:", "UNIQUE_SOLUTION"),
        (r"STOPPED WITH SOLUTION:", "STOPPED_WITH_SOLUTION"),
        (r"FOUND NON-GOAL SOLUTION:", "NON_GOAL_SOLUTION"),
        (r"FOUND MULTIPLE SOLUTIONS:", "MULTIPLE_SOLUTIONS"),
        (r"STALLED WITH PARTIAL SOLUTION:", "PARTIAL_SOLUTION"),
        (r"NO SOLUTION", "NO_SOLUTION"),
        (r"ALTERNATE SOLUTION", "ALTERNATE_SOLUTION"),
        (r"FOUND ONE SOLUTION", "CHECKING_FOR_MORE")
    ]
    
    for pattern, sol_type in solution_type_patterns:
        if re.search(pattern, stdout, re.MULTILINE):
            result["solution_type"] = sol_type
            break
    
    # Extract only the solution (without analyzing statuses)
    solution_lines = []
    capture = False
    for line in stdout.split('\n'):
        if capture and (line.startswith('NO SOLUTION') or line.startswith('FOUND') or 
                       line.startswith('UNIQUE') or not line.strip()):
            capture = False
        if capture:
            solution_lines.append(line)
        if "SOLUTION:" in line:
            capture = True
    
    if solution_lines:
        result["solution"] = '\n'.join(solution_lines)
        
    return result

@app.on_event("startup")
async def startup_event():
    """Create temporary directory at startup"""
    create_temp_directory()

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Endpoint to check if the API is working."""
    return {"status": "ok", "message": "API is running"}

@app.post("/api/solve", response_model=SolverResponse)
async def solve_puzzle(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    check_uniqueness: bool = Form(False),
    check_solution: bool = Form(False),
    use_line_solving: bool = Form(True),
    use_exhaust: bool = Form(True),
    use_contradiction: bool = Form(False),
    use_guessing: bool = Form(True),
    use_probing: bool = Form(True),
    use_merge_probe: bool = Form(False),
    use_caching: bool = Form(True),
    contradiction_depth: int = Form(2),
    cpu_limit: int = Form(0),
    start_solution: int = Form(0),
    puzzle_index: int = Form(1),
    hint_log: bool = Form(False),
    hint_log_n: int = Form(10),
    scoring_rule: Optional[int] = Form(None),
    probing_level: Optional[int] = Form(None)
):
    """
    API for solving nonograms by uploading a file.
    """
    try:
        # Check file extension
        if not "." in file.filename:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File has no extension"
            )
        
        file_format = file.filename.rsplit(".", 1)[1].lower()
        if not is_allowed_file_format(file_format):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File format not supported"
            )
        
        # Generate unique filename
        session_id = str(uuid.uuid4())
        temp_input_path = os.path.join(UPLOAD_FOLDER, f"{session_id}_{file.filename}")
        
        # Save uploaded file
        with open(temp_input_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"Saved input file: {temp_input_path}")
        
        # Preprocess XML file to remove DTD issues
        if file_format.lower() == 'xml':
            preprocess_xml_file(temp_input_path)
        
        # Schedule file removal after completion
        background_tasks.add_task(cleanup_temp_file, temp_input_path)
        
        # Prepare options for pbnsolve
        options = PbnsolveOptions(
            check_uniqueness=check_uniqueness,
            check_solution=check_solution,
            use_line_solving=use_line_solving,
            use_exhaust=use_exhaust,
            use_contradiction=use_contradiction,
            use_guessing=use_guessing,
            use_probing=use_probing,
            use_merge_probe=use_merge_probe,
            use_caching=use_caching,
            contradiction_depth=contradiction_depth,
            cpu_limit=cpu_limit,
            start_solution=start_solution,
            puzzle_index=puzzle_index,
            hint_log=hint_log,
            hint_log_n=hint_log_n,
            scoring_rule=scoring_rule,
            probing_level=probing_level
        )
        
        # Prepare arguments
        pbnsolve_args = create_pbnsolve_args(options, file_format, temp_input_path)
        
        # Run pbnsolve
        logger.info(f"Running command: {' '.join(pbnsolve_args)}")
        process = subprocess.run(pbnsolve_args, capture_output=True, text=True)
        
        # Parse result
        result = parse_pbnsolve_output(process.stdout, process.stderr, process.returncode)
        
        # Return response
        return SolverResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@app.post("/api/solve/text", response_model=SolverResponse)
async def solve_puzzle_text(
    background_tasks: BackgroundTasks,
    puzzle: str = Form(...),
    format: str = Form(...),
    check_uniqueness: bool = Form(False),
    check_solution: bool = Form(False),
    use_line_solving: bool = Form(True),
    use_exhaust: bool = Form(True),
    use_contradiction: bool = Form(False),
    use_guessing: bool = Form(True),
    use_probing: bool = Form(True),
    use_merge_probe: bool = Form(False),
    use_caching: bool = Form(True),
    contradiction_depth: int = Form(2),
    cpu_limit: int = Form(0),
    start_solution: int = Form(0),
    puzzle_index: int = Form(1),
    hint_log: bool = Form(False),
    hint_log_n: int = Form(10),
    scoring_rule: Optional[int] = Form(None),
    probing_level: Optional[int] = Form(None)
):
    """
    API for solving nonograms submitted as text.
    """
    try:
        # Check format
        if not is_allowed_file_format(format):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format not supported"
            )
        
        # Generate unique session identifier
        session_id = str(uuid.uuid4())
        temp_input_path = os.path.join(UPLOAD_FOLDER, f"{session_id}.{format}")
        
        # Save content to temporary file
        with open(temp_input_path, 'w') as f:
            f.write(puzzle)
        logger.info(f"Saved input file from text: {temp_input_path}")
        
        # Preprocess XML file to remove DTD issues
        if format.lower() == 'xml':
            preprocess_xml_file(temp_input_path)
        
        # Schedule file removal after completion
        background_tasks.add_task(cleanup_temp_file, temp_input_path)
        
        # Prepare options for pbnsolve
        options = PbnsolveOptions(
            check_uniqueness=check_uniqueness,
            check_solution=check_solution,
            use_line_solving=use_line_solving,
            use_exhaust=use_exhaust,
            use_contradiction=use_contradiction,
            use_guessing=use_guessing,
            use_probing=use_probing,
            use_merge_probe=use_merge_probe,
            use_caching=use_caching,
            contradiction_depth=contradiction_depth,
            cpu_limit=cpu_limit,
            start_solution=start_solution,
            puzzle_index=puzzle_index,
            hint_log=hint_log,
            hint_log_n=hint_log_n,
            scoring_rule=scoring_rule,
            probing_level=probing_level
        )
        
        # Prepare arguments
        pbnsolve_args = create_pbnsolve_args(options, format, temp_input_path)
        
        # Run pbnsolve
        logger.info(f"Running command: {' '.join(pbnsolve_args)}")
        process = subprocess.run(pbnsolve_args, capture_output=True, text=True)
        
        # Parse result
        result = parse_pbnsolve_output(process.stdout, process.stderr, process.returncode)
        
        # Return response
        return SolverResponse(**result)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )