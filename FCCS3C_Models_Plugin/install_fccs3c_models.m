function install_fccs3c_models(pamFolder)

    % INSTALL_FCCS3C_MODELS  Install the 3C-FCCS fit models into PAM.
    %
    %   install_fccs3c_models              finds PAM (or asks for the folder)
    %   install_fccs3c_models(pamFolder)   installs into the given PAM folder
    %
    % Run it once from this plugin folder. It:
    %   1. copies the 8 FCCS3C_*.m fit models to <PAM>/Models/fcs/
    %   2. copies FCCS3C_Menu.m to <PAM>/
    %   3. adds a few lines to <PAM>/FCSFit.m, so that every FCSFit window gets
    %      "3C-FCCS > Fit models" (a backup FCSFit.m.bak_fccs3c is kept)
    %
    % Running it again updates the models and the menu; FCSFit.m is only
    % changed once. Undo everything with uninstall_fccs3c_models.

    pluginDir = fileparts(mfilename('fullpath'));

    if nargin < 1 || isempty(pamFolder)
        pamFolder = fccs3cFindPam();
        if isempty(pamFolder)
            return
        end
    end

    fcsFitFile = fullfile(pamFolder, 'FCSFit.m');
    modelsDir = fullfile(pamFolder, 'Models', 'fcs');
    if ~exist(fcsFitFile, 'file') || ~exist(modelsDir, 'dir')
        error('fccs3c:notPam', ...
            'This is not a PAM folder (FCSFit.m or Models/fcs is missing):\n%s', pamFolder);
    end

    fprintf('Installing the 3C-FCCS fit models into %s\n', pamFolder);

    % 1. fit models
    models = dir(fullfile(pluginDir, 'models', 'FCCS3C_*.m'));
    if isempty(models)
        error('fccs3c:noModels', 'No FCCS3C_*.m models found in %s', fullfile(pluginDir, 'models'));
    end
    for k = 1:numel(models)
        copyOrFail(fullfile(pluginDir, 'models', models(k).name), fullfile(modelsDir, models(k).name));
    end
    fprintf('  copied %d models to Models/fcs\n', numel(models));

    % model file from an earlier version of these models
    oldModel = fullfile(modelsDir, 'FCS_D_2Component_noBG.m');
    if exist(oldModel, 'file')
        delete(oldModel);
        fprintf('  removed the old FCS_D_2Component_noBG.m (now FCCS3C_2Comp_D)\n');
    end

    % 2. menu
    copyOrFail(fullfile(pluginDir, 'FCCS3C_Menu.m'), fullfile(pamFolder, 'FCCS3C_Menu.m'));
    fprintf('  copied FCCS3C_Menu.m\n');

    % 3. hook in FCSFit.m
    patchFcsFit(fcsFitFile);

    rehash;
    fprintf(['Done. Close all FCSFit windows and open FCSFit again:\n', ...
        '  3C-FCCS > Fit models > 1 component / 2 components\n']);
end

function patchFcsFit(file)

    txt = fileread(file);

    if ~isempty(strfind(txt, 'FCCS3C_Menu('))
        fprintf('  FCSFit.m already loads the menu, not changed\n');
        return
    end

    if ~isempty(strfind(txt, sprintf('\r\n')))
        eol = sprintf('\r\n');
    else
        eol = sprintf('\n');
    end
    lines = regexp(txt, '\r?\n', 'split');

    % The main FCSFit function ends with the last "end" at column 1 before
    % the second "function" line (the first local function).
    isFunction = ~cellfun('isempty', regexp(lines, '^\s*function\s', 'once'));
    functionLines = find(isFunction);
    if numel(functionLines) < 2
        error('fccs3c:patch', ['Could not find the end of the main FCSFit function in\n%s\n', ...
            'Add the FCCS3C_Menu(fig) call by hand (see README.md).'], file);
    end
    k = functionLines(2) - 1;
    while k > functionLines(1) && isempty(regexp(lines{k}, '^end\s*$', 'once'))
        k = k - 1;
    end
    if k == functionLines(1)
        error('fccs3c:patch', ['Could not find the end of the main FCSFit function in\n%s\n', ...
            'Add the FCCS3C_Menu(fig) call by hand (see README.md).'], file);
    end

    hook = { ...
        '', ...
        '    % >>> 3C-FCCS fit models (added by install_fccs3c_models) >>>', ...
        '    if exist(''FCCS3C_Menu'', ''file'')', ...
        '        FCCS3C_Menu(fig);', ...
        '    end', ...
        '    % <<< 3C-FCCS fit models <<<'};
    lines = [lines(1:k-1), hook, lines(k:end)];

    backup = [file, '.bak_fccs3c'];
    if ~exist(backup, 'file')
        copyOrFail(file, backup);
    end

    writeText(file, strjoin(lines, eol));
    fprintf('  added the 3C-FCCS menu hook to FCSFit.m (backup: FCSFit.m.bak_fccs3c)\n');
end

function copyOrFail(source, target)
    [ok, msg] = copyfile(source, target, 'f');
    if ~ok
        error('fccs3c:copy', 'Could not copy\n%s\nto\n%s\n%s', source, target, msg);
    end
end

function writeText(file, txt)
    fid = fopen(file, 'w');
    if fid < 0
        error('fccs3c:write', 'Could not write %s (is it read-only?)', file);
    end
    fwrite(fid, txt, 'char');
    fclose(fid);
end
