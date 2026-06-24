import os
import tempfile
import traceback
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="STL Code Runner API")


# Схема для отправки кода текстом (альтернативный вариант)
class CodePayload(BaseModel):
    code: str


def run_code_and_get_stl(code_text: str) -> str:
    """Выполняет код во временной папке и ищет созданный STL-файл"""
    # Создаем изолированную временную директорию для работы скрипта
    with tempfile.TemporaryDirectory() as tmpdir:
        current_dir = os.getcwd()
        os.chdir(tmpdir)  # Переходим туда, чтобы файлы создавались внутри

        # Контекст для выполнения кода
        local_context = {}

        try:
            # Выполняем динамический код
            exec(code_text, {}, local_context)

            # Ищем, появился ли в папке .stl файл
            files = [f for f in os.listdir(tmpdir) if f.lower().endswith('.stl')]

            if not files:
                raise Exception("Скрипт выполнился успешно, но не создал ни одного .stl файла.")

            # Берем первый попавшийся STL-файл
            generated_file = files[0]

            # Читаем его в глобальную временную директорию ОС, чтобы отдать пользователю
            target_path = os.path.join(tempfile.gettempdir(), f"generated_{generated_file}")
            with open(generated_file, "rb") as f_in, open(target_path, "wb") as f_out:
                f_out.write(f_in.read())

            return target_path

        except Exception as e:
            # Перехватываем полную ошибку и трейсбек
            error_msg = f"{str(e)}\n\nTraceback:\n{traceback.format_exc()}"
            raise RuntimeError(error_msg)
        finally:
            os.chdir(current_dir)  # Возвращаем рабочую директорию назад


@app.post("/run-script-file/", summary="Запуск скрипта из загруженного .py файла")
async def run_script_file(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.py'):
        raise HTTPException(status_code=400, detail="Файл должен иметь расширение .py")

    contents = await file.read()
    code_text = contents.decode("utf-8")

    try:
        stl_path = run_code_and_get_stl(code_text)
        # Отправляем файл пользователю и автоматически удаляем его после отправки
        return FileResponse(
            path=stl_path,
            filename=os.path.basename(stl_path),
            media_type="application/sla",
            background=None
        )
    except RuntimeError as err:
        raise HTTPException(status_code=400, detail=f"Ошибка выполнения скрипта:\n{str(err)}")


# @app.post("/run-script-text/", summary="Запуск скрипта из текста (JSON)")
# async def run_script_text(payload: CodePayload):
#     try:
#         stl_path = run_code_and_get_stl(payload.code)
#         return FileResponse(
#             path=stl_path,
#             filename=os.path.basename(stl_path),
#             media_type="application/sla"
#         )
#     except RuntimeError as err:
#         raise HTTPException(status_code=400, detail=f"Ошибка выполнения скрипта:\n{str(err)}")


# if __name__ == "__main__":
#     import uvicorn
#
#     uvicorn.run(app, host="127.0.0.1", port=8000)