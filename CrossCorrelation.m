function [Cor_Array,Timeaxis] = CrossCorrelation(Data1,Data2,Maxtime,Weights1,Weights2,mode)

[userValues, ~] = UserValues.load();

% Calculates crosscorrelation function of two photon streams.
%
% Args:
%   * Data1, Data2: Cell arrays of photon time stamps for each block
%   * Maxtime: Maximum photon arrival time
%   * Weights1, Weights2: Cell arrays of photon weights. Used for FLCS, defaults to 1)
%   * mode: mode=1 performs normal correlation based on blocks of photon data. mode=2 performs burstwise correlation. In this case, Data1/2 are cell arrays of burstwise photon data. Defaults to 1.
%
% Returns:
%   * Cor_Array: Array of computed correlation functions. Number of correlation curves returned is equal to the number of blocks (mode 1), or equal to 50 in case of burstwise correlation (mode 2).
%   * Timeaxis: Timeaxis for correlation function

sg_fcs = [];
% following code has been commented since it clashes with pCF @Simon
% Wanninger should fix this
% if (size(Data1, 2) > 1) % sg_fcs case
%     prompt = {'Last Gate (Bin number):', 'Step size:'};
%     dlgtitle = 'sg-FCS input';
%     dims = [1 35];
%     definput = {'1000', '10'};
%     step_size = inputdlg(prompt,dlgtitle,dims,definput);
%     step_size = str2double(step_size);
%     sg_fcs = 1;
% end
Maxtime = double(Maxtime);
%%% If no weights are specified, set to 1
if (nargin < 4) || isempty(Weights1)
    Weights1 = cell(numel(Data1),1);
    Weights2 = cell(numel(Data2),1);
    for i = 1:numel(Data1)
        Weights1{i} = ones(numel(Data1{i}),1);
        Weights2{i} = ones(numel(Data2{i}),1);
    end
end

%%% If no mode (BurstCorrelation or not) was specified, default to normal
%%% correlation
if nargin < 6
    mode = 1;
end

%%% Calculates a pseudologarithmic timeaxis:
%%% [0, 1:1:20, 22:2:40, 44:4:80, ....] (slice notation start:step:end)
Time_Bins_Size = 10;
if mode == 1
    Timeaxis_Exponent=floor(log2(Maxtime / Time_Bins_Size)) + 1;
elseif any(mode == [2,3])
    MaxMaxtime = max(Maxtime);
    Timeaxis_Exponent=ceil(log2(double(MaxMaxtime)));
end
Timeaxis_Size = Time_Bins_Size * Timeaxis_Exponent;
Timeaxis = 2.^floor( ( (1:Timeaxis_Size) - 1 ) / Time_Bins_Size - 1)';
Timeaxis(Timeaxis < 1) = 1;
Timeaxis = cumsum([0;Timeaxis]);
%%% The max value of Timeaxis should not exceed the Maxtime
%%% PROOF: (where b = Time_Bins_Size, n = Timeaxis_Exponent)
%%% max(Timeaxis) = Timeaxis(end)
%%% = b * (1 + 1 + 2 + 4 + 8 + ... + 2^(n-1)) + b * 2^n
%%% = 2b * 2^n  <=  2b * 2^(log2(Maxtime / b) + 1 - 2) = Maxtime
%%% Thus, max(Timeaxis) <= Maxtime

Cor_Array=repmat({[]},numel(Data1),1);
parfor (i=1:numel(Data1),userValues.Settings.Pam.ParallelProcessing)
    if ~isempty(Data1{i}) && ~isempty(Data2{i})
        %%% Does the crosscorrelation
        Cor_Array{i} = mexWrapper('Do_CCF', ...
            uint64(Data1{i}), uint64(Data2{i}),...
            double(Weights1{i}), double(Weights2{i}),...
            uint64(Time_Bins_Size), uint64(Timeaxis_Exponent),...
            uint64(numel(Data1{i})), uint64(numel(Data2{i}))...
        );
        Cor_Array{i} = Cor_Array{i}';
    end
end

% remove the zero-delay correlation for backwards compatibility
Timeaxis = Timeaxis(2:end);
for i=1:numel(Cor_Array)
    Cor_Array{i} = Cor_Array{i}(2:end);
end

%%% Does additional normalizing
if mode == 1
    Norm = Maxtime - Timeaxis;
    if Norm < 0
        Norm = 0;
    end

    for i=1:numel(Cor_Array)
        Weights1_Sum = cumsum(Weights1{i});
        Weights2_Sum = [0; cumsum(Weights2{i})];
        Countrate1 = zeros(1,numel(Timeaxis));
        Countrate2 = zeros(1,numel(Timeaxis));
        for j = 1:numel(Timeaxis)
            Stop = find(Data1{i} <= (Maxtime-Timeaxis(j)),1,'last');
            Start = find(Data2{i} >= (Timeaxis(j)),1,'first');
            if ~isempty(Stop)
                Countrate1(j) = Weights1_Sum(Stop)/(Maxtime-Timeaxis(j));
            else
                Countrate1(j) = 0;
            end
            if ~isempty(Start)
                Countrate2(j) = (Weights2_Sum(end)-Weights2_Sum(Start))/(Maxtime-Timeaxis(j));
            else
                Countrate2(j) = 0;
            end       
    %         Countrate1(j) = sum(Weights1{i}(Data1{i} <= (Maxtime-Timeaxis(j))))./(Maxtime-Timeaxis(j));
    %         Countrate2(j) = sum(Weights2{i}(Data2{i} >= (Timeaxis(j))))./(Maxtime-Timeaxis(j));
        end 
        Cor_Array{i} = Cor_Array{i}./Norm./Countrate1'./Countrate2'-1;
    end
    %%% Makes sure all bins have the same size
    Array_Length=cellfun(@numel,Cor_Array);
    if min(Array_Length)~=max(Array_Length)
       for i=1:numel(Cor_Array)
          if Array_Length(i)<max(Array_Length)
              Cor_Array{i}(max(Array_Length))=0;
          end
       end
    end
    Cor_Array=cell2mat(Cor_Array');
    % for i=1:numel(Cor_Array)
    %     Cor_Array{i}=(Cor_Array{i}./(Maxtime-(Timeaxis)))/((sum(Weights1{i})/max(Data1{i}))*(sum(Weights2{i})/max(Data2{i})))-1;
    %     %Cor_Array{i}=(Cor_Array{i}./(Maxtime-Timeaxis))/((numel(Data1{i})/max(Data1{i}))*(numel(Data2{i})/max(Data2{i})))-1;
    %     Cor_Array{i}=Cor_Array{i}(1:find(Cor_Array{i}~=-1,1,'last'));
    % end
    Timeaxis=Timeaxis(1:max(Array_Length));
elseif any(mode == [2,3])
    %%% Does additional normalizing
%     Norm = cell(numel(Cor_Array),1);
%     Countrate1 = cell(numel(Cor_Array),1); 
%     Countrate2 = cell(numel(Cor_Array),1);
%     parfor i=1:numel(Cor_Array)
%         Norm{i} = Maxtime(i)-Timeaxis+1;
%         Norm{i}(Norm{i}<0) = 0;
%         %Norm{i}(Timeaxis>Maxtime(i)) = 0;
%         for j = 1:numel(Timeaxis)
%             Countrate1{i}(j) = sum(Weights1{i}(Data1{i} <= (Maxtime(i)-Timeaxis(j))));
%             Countrate2{i}(j) = sum(Weights2{i}(Data2{i} >= (Timeaxis(j))));
%         end
%          %Countrate1{i} = sum(Weights1{i});
%          %Countrate2{i} = sum(Weights2{i});
%     end
    Norm = cell(numel(Cor_Array),1);
    Countrate1 = cell(numel(Cor_Array),1); 
    Countrate2 = cell(numel(Cor_Array),1);
    parfor (i=1:numel(Cor_Array),userValues.Settings.Pam.ParallelProcessing)
        Norm{i} = Maxtime(i)-Timeaxis+1;
        Norm{i}(Norm{i}<0) = 0;
        Weights1_Sum = cumsum(Weights1{i});
        Weights2_Sum = [0; cumsum(Weights2{i})]; %%% Important here!
        Countrate1{i} = zeros(1,numel(Timeaxis));
        Countrate2{i} = zeros(1,numel(Timeaxis));
        for j = 1:numel(Timeaxis)
            Stop = find(Data1{i} <= (Maxtime(i)-Timeaxis(j)),1,'last');
            Start = find(Data2{i} >= (Timeaxis(j)),1,'first');
            if ~isempty(Stop)
                Countrate1{i}(j) = Weights1_Sum(Stop);
            else
                Countrate1{i}(j) = 0;
            end
            if ~isempty(Start)
                Countrate2{i}(j) = (Weights2_Sum(end)-Weights2_Sum(Start));
            else
                Countrate2{i}(j) = 0;
            end       
    %         Countrate1(j) = sum(Weights1{i}(Data1{i} <= (Maxtime-Timeaxis(j))))./(Maxtime-Timeaxis(j));
    %         Countrate2(j) = sum(Weights2{i}(Data2{i} >= (Timeaxis(j))))./(Maxtime-Timeaxis(j));
        end 
    end
    if mode == 2
        %%% Bootstrapping
        %%% 1) Select Nbursts times out of pool (may select double)
        bootstrap = 50;
        selected = randi(numel(Data1),numel(Data1),bootstrap);

        Cor_Res = cell(1,bootstrap);
        for i = 1:bootstrap
            sel = selected(:,i);
            norm_temp = Norm(sel); norm_temp = sum(horzcat(norm_temp{:}),2);
            Countrate1_temp = Countrate1(sel);Countrate1_temp = sum(vertcat(Countrate1_temp{:}),1);%./sum(Maxtime(sel));
            Countrate2_temp = Countrate2(sel);Countrate2_temp = sum(vertcat(Countrate2_temp{:}),1);%./sum(Maxtime(sel));
            Cor_Total_temp = Cor_Array(sel);Cor_Total_temp = sum(horzcat(Cor_Total_temp{:}),2);
            Cor_Res{i} = Cor_Total_temp.*norm_temp./Countrate1_temp'./Countrate2_temp'-1;
            %Cor_Res{i} = Cor_Total_temp./norm_temp./Countrate1_temp'./Countrate2_temp'-1;
        end

        for i = 1:numel(Cor_Res)
            Cor_Res{i}(~isfinite(Cor_Res{i})) = -1;
            %Cor_Res{i}(find(Cor_Res{i}(~isnan(Cor_Res{i}))==-1,1,'first'):end) = 0;
            %Cor_Res{i}=Cor_Res{i}(1:find(Cor_Res{i}(~isnan(Cor_Res{i}))~=-1,1,'last'));
            Cor_Res{i}((find(Cor_Res{i}~=-1,1,'last')+1):end) = 0;
        end
        Cor_Array = cell2mat(Cor_Res);
        Cor_Array = Cor_Array(1:find(sum(Cor_Array,2),1,'last'),:);
        Timeaxis = Timeaxis(1:size(Cor_Array,1));
    elseif mode == 3
        %%% return the burstwise correlation functions instead of averaging
        Cor_Array = cellfun(@(x,y,z,u) x.*y./z'./u'-1,Cor_Array,Norm,Countrate1,Countrate2,'Uniformoutput',false);
    end
end
