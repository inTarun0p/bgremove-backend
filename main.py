from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from rembg import remove
from io import BytesIO
from PIL import Image
import zipfile
import logging
import os
import uvicorn

app = FastAPI(
    title="Background Removal API",
    description="API for removing backgrounds from images in ZIP files",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to the Background Removal API",
        "usage": {
            "endpoint": "POST /remove-bg-zip/",
            "description": "Upload a ZIP file containing images to remove backgrounds",
            "parameters": {"file": "A ZIP file containing images (JPG, PNG, etc.)"},
            "response": "A ZIP file containing processed images with transparent backgrounds"
        },
        "documentation": "Visit /docs for interactive API documentation"
    }

@app.get("/remove-bg-zip/")
async def get_remove_bg_zip():
    return {
        "message": "Background Removal API",
        "usage": {
            "method": "POST",
            "endpoint": "/remove-bg-zip/",
            "content-type": "multipart/form-data",
            "body": {"file": "A ZIP file containing images (required)"},
            "response": "A ZIP file containing processed images with transparent backgrounds"
        },
        "note": "This endpoint only accepts POST requests for file uploads."
    }

@app.post("/remove-bg-zip/")
async def remove_bg_zip(file: UploadFile = File(None)):
    if not file or not file.filename:
        logger.warning("Request rejected: No file provided or filename is empty")
        raise HTTPException(status_code=400, detail="No file provided")
        
    if not file.filename.lower().endswith('.zip'):
        logger.warning(f"Request rejected: Invalid file type '{file.filename}'. Expected .zip")
        raise HTTPException(status_code=400, detail="File must be a ZIP file")
    
    try:
        # Read file contents and reset file pointer
        contents = await file.read()
        if not contents:
            logger.warning("Request rejected: File content is empty")
            raise HTTPException(status_code=400, detail="The uploaded file is empty")
        
        logger.info(f"Processing file: {file.filename}, size: {len(contents)} bytes")
        output_buffer = BytesIO()
        processed_files = 0

        try:
            # Process ZIP file
            with zipfile.ZipFile(BytesIO(contents), 'r') as zip_ref:
                file_list = zip_ref.namelist()
                if not file_list:
                    logger.warning("Request rejected: ZIP file contains no files")
                    raise HTTPException(status_code=400, detail="ZIP file is empty")
                
                logger.info(f"Found {len(file_list)} files in ZIP")
                
                with zipfile.ZipFile(output_buffer, 'w', zipfile.ZIP_DEFLATED) as out_zip:
                    for file_info in zip_ref.infolist():
                        if file_info.file_size == 0:
                            logger.warning(f"Skipping empty file: {file_info.filename}")
                            continue
                        
                        file_ext = os.path.splitext(file_info.filename)[1].lower()
                        if file_ext in ALLOWED_EXTENSIONS:
                            try:
                                with zip_ref.open(file_info) as img_file:
                                    try:
                                        img = Image.open(img_file).convert('RGBA')
                                        # Remove background
                                        result = remove(img)
                                        # Save processed image
                                        img_byte_arr = BytesIO()
                                        result.save(img_byte_arr, format='PNG')
                                        # Use original filename with .png extension
                                        base = os.path.splitext(file_info.filename)[0]
                                        new_filename = f"{base}.png"
                                        out_zip.writestr(new_filename, img_byte_arr.getvalue())
                                        processed_files += 1
                                        logger.info(f"Processed: {new_filename}")
                                    except Exception as img_error:
                                        logger.warning(f"Error processing {file_info.filename}: {str(img_error)}")
                                        # Include original file in output if processing fails
                                        with zip_ref.open(file_info) as original_file:
                                            out_zip.writestr(file_info.filename, original_file.read())
                            except Exception as e:
                                logger.error(f"Failed to process {file_info.filename}: {str(e)}")
                                continue
            
            if processed_files == 0:
                logger.warning("Request rejected: No valid images processed in ZIP")
                raise HTTPException(status_code=400, detail="No valid images found in the ZIP file")
            
            logger.info(f"Successfully processed {processed_files} out of {len(file_list)} files")
            
            # Prepare response
            output_buffer.seek(0)
            response = StreamingResponse(
                output_buffer,
                media_type="application/zip",
                headers={
                    "Content-Disposition": f"attachment; filename=processed_{os.path.basename(file.filename)}",
                    "Content-Length": str(output_buffer.getbuffer().nbytes)
                }
            )
            
            return response
        
        except zipfile.BadZipFile:
            logger.error("Uploaded file is not a valid ZIP")
            raise HTTPException(status_code=400, detail="Invalid ZIP file format")
            
        except Exception as e:
            logger.error(f"Error processing ZIP file: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)