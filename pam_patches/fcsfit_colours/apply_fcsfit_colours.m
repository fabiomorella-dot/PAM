function apply_fcsfit_colours(pamFolder)

    % apply_fcsfit_colours
    %
    % Makes FCSFit colour every loaded curve by its channels
    % (BB blue, GG green, RR red, BG violet, BR purple, GR dark yellow, BGR dark).
    %
    %   apply_fcsfit_colours                 asks for the PAM folder
    %   apply_fcsfit_colours('C:\...\PAM')   uses that folder
    %
    % It copies FCSFit_ChannelColor.m into the PAM folder and adds a few lines
    % to the place where FCSFit styles newly loaded files. Works with the new
    % FCSFit (2026, functions/FCSFit/...) and with the older single-file FCSFit.m.
    % A backup of the changed file is kept as *.bak. Running it twice is safe.

    here = fileparts(mfilename('fullpath'));
    if nargin < 1 || isempty(pamFolder)
        pamFolder = uigetdir(pwd, 'Select your PAM folder (the one with PAM.m and FCSFit.m)');
        if isequal(pamFolder, 0)
            disp('Cancelled.');
            return;
        end
    end
    pamFolder = char(pamFolder);
    if ~isfile(fullfile(pamFolder, 'FCSFit.m'))
        error('No FCSFit.m in "%s" - please select the PAM folder.', pamFolder);
    end

    copyfile(fullfile(here, 'FCSFit_ChannelColor.m'), fullfile(pamFolder, 'FCSFit_ChannelColor.m'), 'f');
    fprintf('copied FCSFit_ChannelColor.m to %s\n', pamFolder);

    newFile = fullfile(pamFolder, 'functions', 'FCSFit', '+fcs', '+gui', '+cb', 'styleLoadNewFileCallback.m');
    if isfile(newFile)
        % new FCSFit (split into functions/FCSFit/...)
        target = newFile;
        anchor = '    % TODO: integrate this into userValues like 1:8 above';
        hook = { ...
            '    % colour curves by their channels (BB blue, GG green, ...), see FCSFit_ChannelColor.m'
            '    for i = 1:numel(fcsData.fileName)'
            '        color = FCSFit_ChannelColor(fcsData.fileName{i});'
            '        if ~isempty(color)'
            '            Data{i, layout.COL_COLOR} = sprintf(''%g %g %g'', color);'
            '        end'
            '    end'
            ''};
        after = '';
    else
        % older FCSFit: everything in FCSFit.m, function Update_Style, case 1
        target = fullfile(pamFolder, 'FCSFit.m');
        anchor = '        %%% Updates new plots to style';
        hook = { ...
            '        %%% Colour curves by their channels (BB blue, GG green, ...), see FCSFit_ChannelColor.m'
            '        for i=1:numel(FCSData.FileName)'
            '            color = FCSFit_ChannelColor(FCSData.FileName{i});'
            '            if ~isempty(color)'
            '                Data{i,1} = sprintf(''%g %g %g'', color);'
            '            end'
            '        end'};
        after = 'case 1 %%% Called, when new file is loaded';
    end

    fid = fopen(target, 'r', 'n', 'UTF-8');
    text = fread(fid, '*char')';
    fclose(fid);
    if contains(text, 'FCSFit_ChannelColor(')
        fprintf('%s already colours curves by channel - nothing to change.\n', target);
        return;
    end
    lines = regexp(text, '\r?\n', 'split');
    start = 1;
    if ~isempty(after)
        start = find(contains(lines, after), 1);
        if isempty(start)
            error('Could not find "%s" in %s.\nThis FCSFit version is not supported - see README.md for the manual change.', after, target);
        end
    end
    pos = find(strcmp(lines(start:end), anchor), 1) + start - 1;
    if isempty(pos)
        error('Could not find the line\n%s\nin %s.\nThis FCSFit version is not supported - see README.md for the manual change.', anchor, target);
    end

    if contains(text, sprintf('\r\n'))
        eol = sprintf('\r\n');
    else
        eol = newline;
    end
    lines = [lines(1:pos - 1), reshape(hook, 1, []), lines(pos:end)];
    copyfile(target, [target '.bak'], 'f');
    fid = fopen(target, 'w', 'n', 'UTF-8');
    if fid < 0
        error('Cannot write %s (is it read-only?).', target);
    end
    fwrite(fid, strjoin(lines, eol), 'char');
    fclose(fid);
    rehash;
    fprintf('updated %s (backup: %s.bak)\n', target, target);
    disp('Done. Close FCSFit (and PAM) and open it again; newly loaded curves are coloured by channel.');
end
