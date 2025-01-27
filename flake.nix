{
  inputs.nixpkgs.url = "nixpkgs";

  outputs =
    { self, nixpkgs, ... }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      inherit (pkgs) lib;
      inherit (builtins)
        hasAttr
        getAttr
        fromTOML
        readFile
        ;

      pyproject = fromTOML (readFile ./pyproject.toml);
      version = pyproject.tool.poetry.version;

      pythonVersions = with pkgs; [
        python310
        python311
        python312
        python313
      ];
      getPackage =
        p: ps:
        if p == "python" then
          null
        else if hasAttr p pkgs then
          getAttr p pkgs
        else
          getAttr p ps;
      packagesFrom = attr: ps: map (p: getPackage p ps) (lib.attrNames attr);
      pythonPackages = packagesFrom pyproject.tool.poetry.dependencies;
      pythonDevPackages = packagesFrom pyproject.tool.poetry.group.dev.dependencies;

      allVersions =
        f:
        lib.listToAttrs (
          builtins.map (p: {
            name = "reform@${builtins.replaceStrings [ "." ] [ "_" ] p.pythonVersion}";
            value = f p;
          }) pythonVersions
        );

      mkDevShell =
        python:
        pkgs.mkShell {
          name = "reform-${python.name}";
          packages = [
            python
            (pythonPackages python.pkgs)
            (pythonDevPackages python.pkgs)
            pkgs.poetry
          ];

          shellHook = ''
            export PYTHONPATH=$PWD/src''${PYTHONPATH:+:''${PYTHONPATH}}
          '';
        };

      mkPackage =
        python:
        python.pkgs.buildPythonPackage {
          inherit version;

          pname = "reform";
          format = "pyproject";

          buildInputs = with python.pkgs; [ poetry-core ];
          propagatedBuildInputs = pythonPackages python.pkgs;

          src = ./.;

          nativeCheckInputs = pythonDevPackages python.pkgs;
          checkPhase = "pytest $src/tests";
        };

      mkCheck = python: pkgs.runCommand "pytest" {
        propagatedBuildInputs = [
          (python.withPackages (ps: [(self.packages.${system}."reform@${builtins.replaceStrings ["."] ["_"] python.pythonVersion}")]))
          (pythonDevPackages python.pkgs)
        ];
      } "pytest ${./tests} --junit-xml=$out";

      allDevShells = allVersions mkDevShell;
      allPackages = allVersions mkPackage;
      allChecks = allVersions mkCheck;

    in
    {
      checks.${system} = allChecks;

      packages.${system} = {
        default = self.packages.${system}."reform@3_12";
      } // allPackages;

      devShells.${system} = {
        default = self.devShells.${system}."reform@3_10";
      } // allDevShells;
    };
}
