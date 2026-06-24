import os
import subprocess
import tempfile
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.background import BackgroundTasks

app = FastAPI(title="STL Code Runner API")


class CodePayload(BaseModel):
    code: str


def remove_file(path: str):
    """Функция обратного вызова для безопасного удаления файла после отправки"""
    try:
        os.remove(path)
    except Exception:
        pass


def run_code_and_get_stl(code_text: str) -> str:
    # Создаем временную директорию
    tmpdir = tempfile.mkdtemp()
    script_path = os.path.join(tmpdir, "script.py")

    # Записываем код в файл
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(code_text)

    try:
        # Запускаем в отдельном процессе без изменения os.chdir()
        # ВАЖНО: Для продакшена замените ['python'] на вызов docker-контейнера!
        result = subprocess.run(
            ["python", "script.py"],
            cwd=tmpdir,
            capture_output=True,
            text=True,
            timeout=30  # Защита от бесконечных циклов
        )

        if result.returncode != 0:
            raise RuntimeError(f"{result.stderr}")

        # Ищем STL
        files = [f for f in os.listdir(tmpdir) if f.lower().endswith('.stl')]
        if not files:
            raise RuntimeError("Скрипт выполнился, но не создал .stl файл.")

        # Переносим файл в надежное место перед очисткой tmpdir
        generated_file = files[0]
        out_path = os.path.join(tempfile.gettempdir(), f"gen_{os.urandom(4).hex()}_{generated_file}")

        os.rename(os.path.join(tmpdir, generated_file), out_path)
        return out_path

    except subprocess.TimeoutExpired:
        raise RuntimeError("Превышено время ожидания выполнения (30 сек).")
    finally:
        # Гарантированно чистим за собой скрипты
        try:
            os.remove(script_path)
            os.rmdir(tmpdir)
        except Exception:
            pass


@app.post("/run-script-file/", summary="Запуск скрипта из загруженного .py файла")
async def run_script_file(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.py'):
        raise HTTPException(status_code=400, detail="Файл должен иметь расширение .py")

    contents = await file.read()
    code_text = contents.decode("utf-8")

    try:
        stl_path = run_code_and_get_stl(code_text)

        # Добавляем задачу на удаление файла ПОСЛЕ отправки клиенту
        background_tasks.add_task(remove_file, stl_path)

        return FileResponse(
            path=stl_path,
            filename=os.path.basename(stl_path),
            media_type="application/sla"
        )
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=f"Ошибка выполнения:\n{str(err)}")