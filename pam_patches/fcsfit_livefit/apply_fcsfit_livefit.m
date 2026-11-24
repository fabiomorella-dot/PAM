function apply_fcsfit_livefit(pamFolder)

    % apply_fcsfit_livefit
    %
    % Adds a Fit button, a "Live fit" switch and a Stop button to FCSFit.
    %
    %   apply_fcsfit_livefit                 asks for the PAM folder
    %   apply_fcsfit_livefit('C:\...\PAM')   uses that folder
    %
    % It copies FCSFit_LiveFit.m next to FCSFit.m and adds two lines to FCSFit.m
    % so that every FCSFit window gets the controls. A backup of FCSFit.m is
    % kept as FCSFit.m.bak. Running it twice is safe.

    here = fileparts(mfilename('fullpath'));
    if nargin < 1 || isempty(pamFolder)
        pamFolder = uigetdir(pwd, 'Select your PAM folder (the one with PAM.m and FCSFit.m)');
        if isequal(pamFolder, 0)
            disp('Cancelled.');
            return;
        end
    end
    pamFolder = char(pamFolder);

    % find FCSFit.m (PAM folder itself, or anywhere below it)
    target = fullfile(pamFolder, 'FCSFit.m');
    if ~isfile(target)
        found = dir(fullfile(pamFolder, '**', 'FCSFit.m'));
        if isempty(found)
            error('No FCSFit.m in "%s" - please select the PAM folder.', pamFolder);
        end
        target = fullfile(found(1).folder, found(1).name);
    end
    targetFolder = fileparts(target);

    source = fullfile(here, 'FCSFit_LiveFit.m');
    destination = fullfile(targetFolder, 'FCSFit_LiveFit.m');
    if ~isfile(source)
        error('FCSFit_LiveFit.m must be in the same folder as apply_fcsfit_livefit.m (%s).', here);
    end
    if ~strcmpi(char(java.io.File(source).getCanonicalPath()), char(java.io.File(destination).getCanonicalPath()))
        copyfile(source, destination, 'f');
        fprintf('copied FCSFit_LiveFit.m to %s\n', targetFolder);
    end

    fid = fopen(target, 'r', 'n', 'UTF-8');
    text = fread(fid, '*char')';
    fclose(fid);
    if contains(text, 'FCSFit_LiveFit(')
        fprintf('%s already has the live fit - nothing to change.\n', target);
        return;
    end
    lines = regexp(text, '\r?\n', 'split');

    % new FCSFit (2026): right after "guidata(fig, h);" that follows "h.CurrentGui = 'FCS';"
    start = find(strcmp(strtrim(lines), 'h.CurrentGui = ''FCS'';'), 1);
    pos = [];
    if ~isempty(start)
        pos = find(strcmp(strtrim(lines(start:end)), 'guidata(fig, h);'), 1) + start - 1;
        indent = regexp(lines{pos}, '^\s*', 'match', 'once');
        hook = { ...
            [indent '% Fit button + live fitting, see FCSFit_LiveFit.m']
            [indent 'if exist(''FCSFit_LiveFit'', ''file''), FCSFit_LiveFit(fig); end']};
    end
    % older single-file FCSFit: after the first "guidata(h.FCSFit,h);"
    if isempty(pos)
        pos = find(~cellfun(@isempty, regexp(lines, '^\s*guidata\(\s*h\.FCSFit\s*,\s*h\s*\);')), 1);
        if ~isempty(pos)
            indent = regexp(lines{pos}, '^\s*', 'match', 'once');
            hook = { ...
                [indent '%%% Fit button + live fitting, see FCSFit_LiveFit.m']
                [indent 'if exist(''FCSFit_LiveFit'', ''file''), FCSFit_LiveFit(h.FCSFit); end']};
        end
    end
    if isempty(pos)
        error(['Could not find where FCSFit stores its GUI handles in %s.\n' ...
               'This FCSFit version is not supported - see README.md for the manual change.'], target);
    end

    if contains(text, sprintf('\r\n'))
        eol = sprintf('\r\n');
    else
        eol = newline;
    end
    lines = [lines(1:pos), reshape(hook, 1, []), lines(pos + 1:end)];
    copyfile(target, [target '.bak'], 'f');
    fid = fopen(target, 'w', 'n', 'UTF-8');
    if fid < 0
        error('Cannot write %s (is it read-only?).', target);
    end
    fwrite(fid, strjoin(lines, eol), 'char');
    fclose(fid);
    rehash;
    fprintf('updated %s (backup: %s.bak)\n', target, target);
    disp('Done. Close FCSFit and open it again: the Fit / Live fit / Stop controls are right of the fit table.');
end
