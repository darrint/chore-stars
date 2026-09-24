{
  lib,
  python3Packages,
}:
python3Packages.buildPythonApplication {
  pname = "chore-stars";
  version = "0.1.0";
  pyproject = true;

  src = lib.fileset.toSource {
    root = ../.;
    fileset = lib.fileset.unions [
      ../pyproject.toml
      ../chore_stars
      ../tests
    ];
  };

  build-system = [python3Packages.hatchling];

  dependencies = with python3Packages; [
    fastapi
    uvicorn
    jinja2
    sqlalchemy
    psycopg2
    authlib
    httpx
    python-multipart
    pillow
    itsdangerous
    pydantic-settings
    qrcode
  ];

  nativeCheckInputs = with python3Packages; [
    pytest
    httpx
  ];

  pythonImportsCheck = ["chore_stars"];

  checkPhase = ''
    runHook preCheck
    pytest -q
    runHook postCheck
  '';

  meta = {
    description = "Household participation board. Stars only.";
    mainProgram = "chore-stars";
  };
}
