{
  lib
, buildPythonPackage
, setuptools
, src
}:

buildPythonPackage rec {
  pname = "exfat-raw";
  version = "0.1.2";
  pyproject = true;

  inherit src;

  nativeBuildInputs = [ setuptools ];
  doCheck = true;
  pythonImportsCheck = [ "exfat_raw" ];

  checkPhase = ''
    runHook preCheck
    python -m unittest discover -s tests -p 'test_exfat_raw_image.py' -v
    runHook postCheck
  '';

  meta = with lib; {
    description = "Raw block-level read/write of exFAT filesystem timestamps (birth time, modification time)";
    longDescription = ''
      exfat-raw is a Python library for raw block-level reading and writing
      of exFAT filesystem timestamps, including birth time (btime/creation timestamp)
      and modification time.
    '';
    homepage = "https://github.com/MBanucu/exfat-raw";
    license = licenses.gpl3Only;
    maintainers = with maintainers; [ ];
  };
}
