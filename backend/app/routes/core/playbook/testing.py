"""
Playbook smoke testing endpoints
"""

import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, Path, UploadFile, File

logger = logging.getLogger(__name__)

router = APIRouter(tags=["playbooks-testing"])


@router.get("/smoke-test/supported", response_model=List[str])
async def get_supported_smoke_test_playbooks():
    """
    Get list of playbooks that support smoke testing

    Returns a list of playbook codes that have smoke tests available.
    """
    return [
        "pdf_ocr_processing",
        "ig_post_generation",
        "yt_script_generation",
        "yearly_book_content_save",
    ]


@router.post("/{playbook_code}/smoke-test/upload-files", response_model=Dict[str, Any])
async def upload_test_files(
    playbook_code: str,
    files: List[UploadFile] = File(...),
    profile_id: str = Query('test-user', description="Profile ID for testing")
):
    """
    Upload test files for playbook smoke test

    This endpoint allows uploading test files (e.g., PDFs) that will be saved
    to the test data directory and used for smoke testing.
    """
    from pathlib import Path
    import shutil

    try:
        backend_dir = Path(__file__).parent.parent.parent.parent
        test_data_dir = backend_dir.parent / "test_data"

        playbook_test_dir = test_data_dir / playbook_code
        playbook_test_dir.mkdir(parents=True, exist_ok=True)

        uploaded_files = []

        for file in files:
            filename = file.filename or "uploaded_file"
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{filename}"
            file_path = playbook_test_dir / safe_filename

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append({
                "original_filename": filename,
                "saved_path": str(file_path),
                "size": file_path.stat().st_size
            })

            logger.info(f"Uploaded test file: {filename} -> {file_path}")

        return {
            "playbook_code": playbook_code,
            "uploaded_files": uploaded_files,
            "test_data_dir": str(playbook_test_dir),
            "message": f"Successfully uploaded {len(uploaded_files)} file(s)"
        }

    except Exception as e:
        logger.error(f"Error uploading test files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to upload files: {str(e)}")


@router.post("/{playbook_code}/smoke-test", response_model=Dict[str, Any])
async def run_playbook_smoke_test(
    playbook_code: str,
    profile_id: str = Query('test-user', description="Profile ID for testing"),
    use_uploaded_files: bool = Query(False, description="Use files uploaded via upload-files endpoint")
):
    """
    Run smoke test for a specific playbook

    This endpoint runs a quick smoke test to verify the playbook works correctly.
    Returns test results including status, outputs, and any errors.
    """
    test_class_map = {
        "pdf_ocr_processing": "TestPdfOcrProcessing",
        "ig_post_generation": "TestIgPostGeneration",
        "yt_script_generation": "TestYtScriptGeneration",
        "yearly_book_content_save": "TestYearlyBookContentSave",
    }

    if playbook_code not in test_class_map:
        raise HTTPException(
            status_code=404,
            detail=f"Smoke test not available for playbook: {playbook_code}. Available playbooks: {', '.join(test_class_map.keys())}"
        )

    try:
        import sys
        from pathlib import Path

        backend_dir = Path(__file__).parent.parent.parent.parent
        tests_dir = backend_dir.parent / "tests"
        if str(tests_dir) not in sys.path:
            sys.path.insert(0, str(tests_dir))

        try:
            if playbook_code == "pdf_ocr_processing":
                from tests.test_playbook_pdf_ocr_processing import TestPdfOcrProcessing
                test_class = TestPdfOcrProcessing
            elif playbook_code == "ig_post_generation":
                from tests.test_playbook_ig_post_generation import TestIgPostGeneration
                test_class = TestIgPostGeneration
            elif playbook_code == "yt_script_generation":
                from tests.test_playbook_yt_script_generation import TestYtScriptGeneration
                test_class = TestYtScriptGeneration
            elif playbook_code == "yearly_book_content_save":
                from tests.test_playbook_yearly_book_content_save import TestYearlyBookContentSave
                test_class = TestYearlyBookContentSave
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"Test class not found for playbook: {playbook_code}"
                )

            test = test_class(profile_id=profile_id)

            if use_uploaded_files and playbook_code == "pdf_ocr_processing":
                backend_dir = Path(__file__).parent.parent.parent.parent
                test_data_dir = backend_dir.parent / "test_data"
                playbook_test_dir = test_data_dir / playbook_code

                if playbook_test_dir.exists():
                    pdf_files = list(playbook_test_dir.glob("*.pdf"))
                    if pdf_files:
                        def get_test_inputs_with_uploaded():
                            docker_paths = []
                            for f in pdf_files[:2]:
                                if str(f).startswith(str(test_data_dir)):
                                    rel_path = f.relative_to(test_data_dir)
                                    docker_path = f"/app/backend/test_data/{playbook_code}/{rel_path.name}"
                                else:
                                    docker_path = str(f)
                                docker_paths.append(docker_path)
                            return {
                                "pdf_files": docker_paths,
                                "dpi": 300,
                                "output_format": "text"
                            }
                        test.get_test_inputs = get_test_inputs_with_uploaded

            result = await test.run_test()

            return {
                "playbook_code": playbook_code,
                "test_status": result.get("status", "unknown"),
                "test_results": result,
                "summary": test.get_test_summary()
            }

        except ImportError as e:
            logger.error(f"Failed to import test class: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Failed to import test class: {str(e)}"
            )
        except Exception as e:
            logger.error(f"Test execution failed: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Test execution failed: {str(e)}"
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Error running smoke test: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
