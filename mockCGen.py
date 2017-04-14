#!/usr/bin/python
"""
The MIT License (MIT)

Copyright (c) 2017 Howard Chan
https://github.com/howard-chan/mockCGen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
import re
import sys
import argparse

# For Debug
import logging
import traceback

class MockCGen:
    '''
    @brief      Generates Interface Class and Fake Stubs:

    @details    Part 1: Build function list by parsing C headers
                Part 2: Generate pure virtual class header and fakes source
                files
    '''
    #====RE objects for parsing header files====
    #----RE match for <return type> <func name> (<arguments>);----
    # e.g.          "void          reset      (bool bTrue);"
    pattFunc = re.compile(r'^\s*?(?=\w)(.*?)(\w*?)\s*?\((.*?)\);', re.MULTILINE)
    # Start of string       ^
    # Consume any space      \x*?
    # Lookahead for words        (?=\w)
    # Group1 (return type)             (.*?)
    # Group2 (func name)                    (\w*?)
    # Space between                               \s*?
    # Group3 (argument)                               \((.*?)\);
    #----RE match for ..)..(..  pattern----
    # e.g.     "*ledCB)(bool bOn)"
    pattBadParenthesis = re.compile(r'^[^(]*(?=\))')
    # Start of string          ^
    # Match any except '('             [^(]*
    # Before matching ')'                   (?=\))
    #----RE match for argument (i.e. last word in definition (e.g. volatile uint16_t **ppusValue))----
    pattArg = re.compile(r'(\w+)$')
    #----RE match for '...' in the arguments----
    pattArgEllipsis = re.compile('\.{3}')
    #----RE match for function pointer 'type (*func_ptr)(...)' in the arguments----
    pattArgPFunc = re.compile('(\w*)\)\s*?\(')
    # Search for a word        (\w*)
    # That is before ") ("          \)\s*?\(

    #====Objects for file generation====
    # Defining the message and file lists
    fileList = []
    fileDict = {}

    def ParseHeader(self, fileName, header):
        '''
        @brief      Parses the header file to be used in GMOCK generation

        @details    Parses "C" headers ".h" and adds function declarations into
                    file List and Dictionary which shall be used to generate
                    GMOCK compatible files

        @param      self      The object
        @param      fileName  Name of file to parse
        @param      header    The header
        '''
        funcList = []
        # Step 1: Parse the file for lines that match the function declaration
        match = self.pattFunc.findall(header)
        for func in match:
            # Step 1.1: Process the components of the matched function declaration
            returnField, funcField, argsField = func[0], func[1], func[2]
            # Check that the fields are valid (i.e. a bad match will have empty fields)
            if len(returnField.lstrip(' ')) == 0 or \
               len(funcField.lstrip(' ')) == 0 or \
               len(argsField.lstrip(' ')) == 0:
                continue
            # Check that there are no bad parenthesis (e.g. when the pattern gets fooled)
            elif self.pattBadParenthesis.search(argsField) or \
                 self.pattBadParenthesis.search(funcField):
                continue
            # Step 1.2: Remove extern specifier if any, since they aren't used in classes
            returnField = returnField.replace('extern','')
            # Step 1.3: Add new tuple to list
            funcList.append((returnField, funcField, argsField))
        # Step 2: Add to fileList and dictionary if functions were found
        if funcList:
            self.fileList.append(fileName)
            self.fileDict[fileName] = funcList

    def ParseArgs(self, args):
        '''
        @brief      Parses the function argument string to a list of argument
                    identifiers only. The argument type is removed

        @param      self  The object
        @param      args  The argument string

        @return     argument string that is passed to the callee
        '''
        strList = []
        try:
            argList = args.split(',')
            for arg in argList:
                match1 = self.pattArg.search(arg)
                match2 = self.pattArgPFunc.search(arg)
                if match1:
                    # Sanitize the argument
                    arg = match1.group(1)
                    if arg == 'void':
                        arg = ''
                    strList.append(arg)
                elif match2:
                    strList.append(match2.group(1))
        except:
            logging.error(traceback.format_exc())
        # Return the comma separate string from list
        return ', '.join(strList)

    def BuildMockCHeader(self, file, className):
        '''
        @brief      Builds a mock c header.

        @param      self       The object
        @param      file       The file
        @param      className  The class name
        '''
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('//DO NOT MODIFY--This is an autogenerated file--DO NOT MODIFY//\n')
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('#ifndef __%s_H__\n' % className.upper())
        file.write('#define __%s_H__\n' % className.upper())
        file.write('\n')
        file.write('#include <gmock/gmock.h>\n')
        file.write('#include <gtest/gtest.h>\n')
        file.write('#include <stdint.h>\n')
        file.write('\n')
        file.write('extern "C"\n')
        file.write('{\n')
        file.write('\n')
        # Generate include files
        file.write('// Include header files that are mocked\n')
        for header in self.fileList:
            file.write('#include "%s"\n' % header)
        file.write('\n')
        # ----Generate the virtual class----
        file.write('// The virtual class\n')
        file.write('class I%s\n' % className)
        file.write('{\n')
        file.write('public:\n')
        file.write('    // Destructor required for gmock\n')
        file.write('    virtual ~I%s() { }\n' % className)
        for fileName in self.fileList:
            file.write('\n    // From %s\n' % fileName)
            # Add the virtual members
            funcList = self.fileDict[fileName]
            for func in funcList:
                returnField, funcField, argsField = func[0], func[1], func[2]
                # Write the virtual member
                file.write('    virtual %s%s(%s) = 0;\n' % (returnField, funcField, argsField))
        file.write('};\n')
        file.write('\n')
        # Add include for post generated GMock file
        file.write('// This file is post generated by Google\'s gmock_gen.py\n')
        file.write('#include "%s.hpp"\n' % className)
        file.write('\n')
        file.write('} // extern "C"\n')
        file.write('#endif // __%s_H__\n' % className.upper())

    def BuildMockCSource(self, file, className):
        '''
        @brief      Builds a mock c source.

        @param      self       The object
        @param      file       The file
        @param      className  The class name
        '''
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('//DO NOT MODIFY--This is an autogenerated file--DO NOT MODIFY//\n')
        file.write('///////////////////////////////////////////////////////////////\n')
        file.write('\n')
        file.write('#include <stdint.h>\n')
        file.write('#include "etypes.h"\n')
        file.write('#include "%s.h"\n' % className)
        file.write('\n')
        file.write('extern "C"\n')
        file.write('{\n')
        file.write('\n')
        # Create mock instance
        file.write('using namespace ::testing;\n')
        file.write('MockI%s _%s;\n' % (className, className))
        file.write('\n')
        # Generate the fake functions
        for fileName in self.fileList:
            file.write('\n// From %s\n' % fileName)
            funcList = self.fileDict[fileName]
            for func in funcList:
                returnField, funcField, argsField = func[0], func[1], func[2]
                if self.pattArgEllipsis.search(argsField):
                    file.write("// Can't generate fake functions that uses '...' in arguments\n")
                    file.write('// WEAK %s%s(%s) { }\n\n' % (returnField, funcField, argsField))
                else:
                    file.write('WEAK %s%s(%s)\n' % (returnField, funcField, argsField))
                    file.write('{\n')
                    # Generate the arguments
                    argsStr = self.ParseArgs(argsField)
                    # Generate call string
                    callStr = '_%s.%s(%s);\n' % (className, funcField, argsStr)
                    # Check if a return is required (i.e. not void or has pointer)
                    if func[0].find('void') < 0 or returnField.find('*') >= 0:
                        callStr = 'return ' + callStr
                    # Write out call string
                    file.write('    %s' % callStr)
                    file.write('}\n\n')
        file.write('} // extern "C"\n')

def main(args):
    # Process the command line arguments
    parser = argparse.ArgumentParser(description="Generates GMOCK files from 'C' header files")
    parser.add_argument('-l', '--list', action="store", help="Build mock functions from file list")
    parser.add_argument('-m', '--mock', action="store", default="mock", help="Base name for class and files")
    parser.add_argument('-p', '--path', action="store", help="Output path")
    parser.add_argument('fileList', nargs='*')
    args = parser.parse_args()

    # Check the source of the headers
    if (args.list):
        with open(args.list) as file:
            for filename in file:
                args.fileList.append(filename)
        file.closed

    # Process the fileList
    if args.fileList:
        print "\tGenerating Mocks:"
        # Build the mock list
        mcg = MockCGen()
        for filename in args.fileList:
            with open(filename.strip('\n')) as f:
                print "\t\tProcessing %s" % filename.strip('\n')
                mcg.ParseHeader(filename, f.read())
            f.closed
        # Save the mock header file
        savename = args.path + args.mock + ".h"
        with open(savename, 'wb') as f:
            mcg.BuildMockCHeader(f, args.mock)
            print '\tSaved to "%s"' % savename
        f.closed
        # Save the mock source file
        savename = args.path + args.mock + ".cpp"
        with open(savename, 'wb') as f:
            mcg.BuildMockCSource(f, args.mock)
            print '\tSaved to "%s"' % savename
        f.closed
    else:
        parser.print_help()

if __name__ == '__main__':
    main(sys.argv[1:])