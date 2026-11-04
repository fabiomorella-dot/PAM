function FCCS3C_Menu(fig)

    % FCCS3C_Menu
    %
    % Adds the 3C-FCCS fit models (Models/fcs/FCCS3C_*.m) to the "3C-FCCS"
    % menu of an FCSFit window, under "3C-FCCS > Fit models". Clicking a
    % model loads it into the fit table, exactly like File > Load Fit Function.
    % If the window has no "3C-FCCS" menu, one is created.
    %
    % Usage:
    %   FCCS3C_Menu(fig)   % fig = an FCSFit figure
    %   FCCS3C_Menu        % adds the menu to every open FCSFit window
    %
    % To get the menu every time FCSFit opens, add the line
    %   FCCS3C_Menu(fig);
    % at the end of the main FCSFit function in FCSFit.m (see Models/README.md).

    if nargin < 1 || isempty(fig)
        fig = findobj(groot, 'Type', 'figure', 'Tag', 'FCSFit');
        if isempty(fig)
            warning('FCCS3C_Menu:noWindow', 'No FCSFit window is open.');
            return
        end
    end

    for f = reshape(fig, 1, [])
        addMenu(f);
    end
end

function addMenu(fig)

    % find the existing "3C-FCCS" menu in the menu bar, or create it
    menu = [];
    topLevel = allchild(fig);
    for m = reshape(topLevel, 1, [])
        if isa(m, 'matlab.ui.container.Menu') && contains(upper(m.Text), '3C')
            menu = m;
            break
        end
    end
    if isempty(menu)
        menu = uimenu(fig, 'Text', '3C-FCCS');
    end

    % remove an older copy, e.g. when this function is called twice
    delete(findall(menu, 'Tag', 'FCCS3C_Models'));

    if isempty(menu.Children)
        separator = 'off';
    else
        separator = 'on';
    end

    root = uimenu(menu, ...
        'Text', 'Fit models', ...
        'Tag', 'FCCS3C_Models', ...
        'Separator', separator, ...
        'Callback', @(src, ~) markCurrent(ancestor(src, 'figure')));

    models = { ...
        '1 component', { ...
            'D  (w_r, w_z fixed)',                    'FCCS3C_1Comp_D'; ...
            'D  (w_r, w_z fixed)  + background',      'FCCS3C_1Comp_D_BG'; ...
            'tauD, p',                                'FCCS3C_1Comp_TauD'; ...
            'tauD, p  + background',                  'FCCS3C_1Comp_TauD_BG'}; ...
        '2 components', { ...
            'D1, D2  (w_r, w_z fixed)',               'FCCS3C_2Comp_D'; ...
            'D1, D2  (w_r, w_z fixed)  + background', 'FCCS3C_2Comp_D_BG'; ...
            'tauD1, tauD2  (p fixed)',                'FCCS3C_2Comp_TauD'; ...
            'tauD1, tauD2  (p fixed)  + background',  'FCCS3C_2Comp_TauD_BG'}};

    for i = 1:size(models, 1)
        sub = uimenu(root, 'Text', models{i, 1});
        list = models{i, 2};
        for j = 1:size(list, 1)
            uimenu(sub, ...
                'Text', list{j, 1}, ...
                'Tag', 'FCCS3C_ModelItem', ...
                'UserData', list{j, 2}, ...
                'Callback', {@loadModel, list{j, 2}});
        end
    end

    uimenu(root, ...
        'Text', 'How to use the 3C switch and background...', ...
        'Separator', 'on', ...
        'Callback', @showHelp);

    markCurrent(fig);
end

function loadModel(src, ~, name)

    fig = ancestor(src, 'figure');
    file = fullfile(getAppFolder(), 'Models', 'fcs', [name, '.m']);

    if ~isfile(file)
        errordlg(sprintf(['Model file not found:\n%s\n\n', ...
            'Copy the FCCS3C_*.m files into the Models/fcs folder of PAM.'], file), ...
            '3C-FCCS');
        return
    end

    % FCSFit loads the model stored as "last used model" when it is not asked
    % to open a file dialog, so store the chosen model there and reload.
    [userValues, ~] = UserValues.load();
    userValues.File.FCS_Standard = file;
    clear userValues % writes the change to the profile

    fcs.gui.cb.loadFitCallback(fig, [], false);

    markCurrent(fig);
end

function markCurrent(fig)

    % put a check mark next to the model that is currently loaded
    items = findall(fig, 'Tag', 'FCCS3C_ModelItem');
    if isempty(items)
        return
    end

    current = '';
    try
        [~, current] = fileparts(fig.UserData.meta.model.name);
    catch
    end

    for item = reshape(items, 1, [])
        item.Checked = strcmp(item.UserData, current);
    end
end

function showHelp(~, ~)

    msg = { ...
        '3C (0/1) column', ...
        '  0 = autocorrelation (GG, RR, BB) or 2-colour cross-correlation (GR, GB, RB)', ...
        '  1 = 3-colour triple correlation (diagonal tau1 = tau, tau2 = 2*tau)', ...
        '  Keep it fixed (F ticked). You can set it per file, so ACFs, CCFs and the', ...
        '  triple correlation can be fitted in the same session (e.g. with D global).', ...
        '', ...
        'Background models (+ background)', ...
        '  Counts_a, BG_a, Counts_b, BG_b, Counts_c, BG_c: count rate and background in kHz.', ...
        '  These are inputs: keep them fixed.', ...
        '  Autocorrelation: same channel in a and b.', ...
        '  2-colour cross-correlation: one channel in a, the other in b.', ...
        '  Channel c is only used when 3C = 1.', ...
        '', ...
        'Models without background: N is the apparent (uncorrected) number.'};
    msgbox(msg, '3C-FCCS models', 'help');
end
