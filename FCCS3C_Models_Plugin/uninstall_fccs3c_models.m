function uninstall_fccs3c_models(pamFolder)

    % UNINSTALL_FCCS3C_MODELS  Remove the 3C-FCCS fit models from PAM.
    %
    %   uninstall_fccs3c_models              finds PAM (or asks for the folder)
    %   uninstall_fccs3c_models(pamFolder)   uses the given PAM folder
    %
    % Deletes the FCCS3C_*.m models from <PAM>/Models/fcs, deletes
    % <PAM>/FCCS3C_Menu.m and removes the lines install_fccs3c_models added
    % to FCSFit.m.

    pluginDir = fileparts(mfilename('fullpath'));

    if nargin < 1 || isempty(pamFolder)
        pamFolder = fccs3cFindPam();
        if isempty(pamFolder)
            return
        end
    end

    fprintf('Removing the 3C-FCCS fit models from %s\n', pamFolder);

    models = dir(fullfile(pluginDir, 'models', 'FCCS3C_*.m'));
    removed = 0;
    for k = 1:numel(models)
        target = fullfile(pamFolder, 'Models', 'fcs', models(k).name);
        if exist(target, 'file')
            delete(target);
            removed = removed + 1;
        end
    end
    fprintf('  removed %d models from Models/fcs\n', removed);

    menuFile = fullfile(pamFolder, 'FCCS3C_Menu.m');
    if exist(menuFile, 'file')
        delete(menuFile);
        fprintf('  removed FCCS3C_Menu.m\n');
    end

    fcsFitFile = fullfile(pamFolder, 'FCSFit.m');
    if exist(fcsFitFile, 'file')
        txt = fileread(fcsFitFile);
        % the hook block plus the blank line the installer put before it
        pattern = '(\r?\n)?\r?\n[^\r\n]*>>> 3C-FCCS fit models.*?<<< 3C-FCCS fit models <<<[^\r\n]*';
        newTxt = regexprep(txt, pattern, '', 'once');
        if ~strcmp(newTxt, txt)
            fid = fopen(fcsFitFile, 'w');
            if fid < 0
                error('fccs3c:write', 'Could not write %s', fcsFitFile);
            end
            fwrite(fid, newTxt, 'char');
            fclose(fid);
            fprintf('  removed the 3C-FCCS menu hook from FCSFit.m\n');
        elseif ~isempty(strfind(txt, 'FCCS3C_Menu('))
            fprintf(['  FCSFit.m still calls FCCS3C_Menu (added by hand). It is harmless\n', ...
                '  without FCCS3C_Menu.m, or delete those lines yourself.\n']);
        end
    end

    rehash;
    fprintf('Done. Close and reopen FCSFit.\n');
end
