function pamFolder = fccs3cFindPam()

    % FCCS3CFINDPAM  Locate the PAM folder for install/uninstall_fccs3c_models.
    %
    % Uses the PAM that MATLAB finds on its path (the folder with FCSFit.m and
    % Models/fcs). If there is none, asks for the folder. Returns '' when the
    % user cancels.

    pamFolder = '';
    pluginDir = fileparts(mfilename('fullpath'));

    found = which('FCSFit');
    if ~isempty(found)
        candidate = fileparts(found);
        if ~strcmp(candidate, pluginDir) && exist(fullfile(candidate, 'Models', 'fcs'), 'dir')
            pamFolder = candidate;
            fprintf('PAM found at %s\n', pamFolder);
            return
        end
    end

    chosen = uigetdir(pwd, 'Select the PAM folder (the one that contains FCSFit.m)');
    if isequal(chosen, 0)
        disp('Cancelled.');
        return
    end
    pamFolder = chosen;
end
