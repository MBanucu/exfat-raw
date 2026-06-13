{
  lib
, buildPythonPackage
, setuptools
, fetchurl
, src
}:

let
  rawblock_io = buildPythonPackage rec {
    pname = "rawblock-io";
    version = "0.1.0";
    src = fetchurl {
      url = "https://files.pythonhosted.org/packages/source/r/rawblock-io/rawblock_io-${version}.tar.gz";
      sha256 = "a68b5a019d4d29d92e39504d6f057660d2d62307d7a7d429d03647ce42b1c7e1";
    };
    pyproject = true;
    nativeBuildInputs = [ setuptools ];
  };
in
buildPythonPackage rec {
  pname = "exfat-raw";
  version = "0.2.1";
  pyproject = true;

  inherit src;

  nativeBuildInputs = [ setuptools ];
  propagatedBuildInputs = [ rawblock_io ];
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
